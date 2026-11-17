"""Stablecoin rates: parsing each exchange, the premium over the official rate, and dropping thin books."""
from src.engines import stablecoins as sc

QUIDAX = {"status": "success", "data": {"at": 1794884454, "ticker": {"buy": "1422.64", "sell": "1428.35", "last": "1426.34", "vol": "33556.05"}, "market": "usdtngn"}}
VALR = {"currencyPair": "USDTZAR", "askPrice": "17.0521", "bidPrice": "17.052", "lastTradedPrice": "17.052", "baseVolume": "14277189.7", "created": "2026-11-17T03:00:08.497Z"}


def test_parse_and_premium():
    ng = sc.with_premium(sc.parse_quidax(QUIDAX), {"NGN": 1352.107942})
    assert ng["pair"] == "USDT/NGN" and ng["rate"] == 1426.34
    assert ng["premium"] == round(1426.34 / 1352.107942 - 1, 4)      # about 5.5%
    assert 0 < ng["spread"] < 0.01
    za = sc.with_premium(sc.parse_valr(VALR), {"ZAR": 16.933937})
    assert za["currency"] == "ZAR" and abs(za["premium"]) < 0.01


def test_missing_official_rate_and_bad_payloads():
    assert sc.with_premium(sc.parse_valr(VALR), {})["premium"] is None
    assert sc.parse_quidax({"data": {"ticker": {"last": "0"}}}) is None
    assert sc.parse_valr({}) is None


def test_thin_books_and_failed_sources_are_left_out():
    class Resp:
        def __init__(self, status, body): self.status_code, self._b = status, body
        def json(self): return self._b

    class Client:
        def get(self, url):
            if "quidax" in url:
                return Resp(200, {"data": {"ticker": {"last": "1500", "vol": "120"}}})   # 120 USDT traded: too thin
            return Resp(503, {})
    out = sc.fetch({"NGN": 1350}, client=Client())
    assert out["rates"] == [] and "Nigeria" in out["method"]


LUNO_ZAR = {"pair": "USDTZAR", "timestamp": 1794907167927, "bid": "17.0183", "ask": "17.021", "last_trade": "17.0183",
            "rolling_24_hour_volume": "1064848.62", "status": "ACTIVE"}
LUNO_NGN = {"pair": "USDTNGN", "last_trade": "1437.98", "rolling_24_hour_volume": "150704.2", "status": "ACTIVE"}


def test_luno_ticker():
    za = sc.parse_luno(LUNO_ZAR)
    assert (za["currency"], za["pair"], za["rate"], za["source"]) == ("ZAR", "USDT/ZAR", 17.0183, "Luno")
    assert sc.parse_luno({"pair": "USDTKES", "last_trade": "135"}) is None      # not a covered market
    assert sc.parse_luno({**LUNO_ZAR, "status": "POSTONLY"}) is None


def test_deeper_book_sets_the_rate_and_the_other_is_a_check():
    rows = sc.combine([sc.parse_quidax(QUIDAX), sc.parse_luno(LUNO_NGN), sc.parse_valr(VALR), sc.parse_luno(LUNO_ZAR)])
    ng, za = rows
    assert ng["source"] == "Luno" and ng["checks"][0]["source"] == "Quidax"     # 150k USDT against 34k
    assert za["source"] == "VALR" and za["checks"] == [{"source": "Luno", "source_url": "https://www.luno.com/",
                                                         "rate": 17.0183, "volume_usdt_24h": 1064848.62}]


def test_one_exchange_failing_keeps_the_market():
    class Resp:
        def __init__(self, status, body): self.status_code, self._b = status, body
        def json(self): return self._b

    class Client:
        def get(self, url):
            if "valr" in url or "quidax" in url:
                return Resp(503, {})
            return Resp(200, LUNO_ZAR if "USDTZAR" in url else LUNO_NGN)
    out = sc.fetch({"NGN": 1352.1, "ZAR": 16.93}, client=Client())
    assert [r["source"] for r in out["rates"]] == ["Luno", "Luno"] and out["complete"] is True
    assert all(r["checks"] == [] for r in out["rates"])


def test_a_missing_market_marks_the_result_incomplete():
    class Resp:
        def __init__(self, status, body): self.status_code, self._b = status, body
        def json(self): return self._b

    class Client:
        def get(self, url):
            return Resp(200, QUIDAX) if "quidax" in url else Resp(404, {})
    out = sc.fetch({"NGN": 1352.1}, client=Client())
    assert [r["currency"] for r in out["rates"]] == ["NGN"] and out["complete"] is False
