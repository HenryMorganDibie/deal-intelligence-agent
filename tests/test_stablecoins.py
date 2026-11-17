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
