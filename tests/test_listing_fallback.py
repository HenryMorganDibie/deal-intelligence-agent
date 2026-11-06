from datetime import date

import httpx

from src.engines import markets

PREVIOUS = [
    {"symbol": "MTNN", "name": "MTN Nigeria", "price": 825.0, "date": "2026-10-29", "shares": 20_354_513_050,
     "mcap": 16_792_473_266_250.0, "ytd": 0.62, "chg_1d": 0.01},
    {"symbol": "OKOMUOIL", "name": "Okomu Oil", "price": 1000.0, "date": "2026-10-29", "mcap": 953_910_000_000.0,
     "ytd": 0.10},
    {"symbol": "QUIET", "name": "No trade today", "price": 5.0, "date": "2026-10-29", "ytd": 0.0},
]
OFFICIAL = [
    {"Symbol": "MTNN", "ClosePrice": 837.0, "PrevClosingPrice": 830.0, "Volume": 1000, "Value": 837000.0,
     "Trades": 12, "TradeDate": "2026-11-06T00:00:00", "Sector": "ICT"},
    {"Symbol": "OKOMUOIL", "ClosePrice": 1100.0, "PrevClosingPrice": 1100.0, "TradeDate": "2026-11-06T00:00:00"},
    {"Symbol": "QUIET", "ClosePrice": None, "PrevClosingPrice": 5.0, "TradeDate": "2026-11-06T00:00:00"},
]


def _client(listing_up: bool) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if "doclib.ngxgroup.com" in str(request.url):
            return httpx.Response(200, json=OFFICIAL)
        return httpx.Response(200, text="<html>listing</html>" if listing_up else "<html>Maintenance</html>")
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ngx_is_repriced_from_the_official_list_when_the_listing_site_is_down():
    quotes, _ = markets.fetch_exchange(markets.EXCHANGES["ngx"], _client(False), date(2026, 11, 6), PREVIOUS)
    by = {q["symbol"]: q for q in quotes}
    assert len(quotes) == 3 and all("_old_price" not in q for q in quotes)
    mtn = by["MTNN"]
    assert mtn["price"] == 837.0 and mtn["date"] == "2026-11-06" and mtn["volume"] == 1000
    assert mtn["mcap"] == round(20_354_513_050 * 837.0, 2)                 # from shares outstanding
    assert abs(mtn["ytd"] - ((1.62 * 837 / 825) - 1)) < 1e-6
    assert abs(mtn["chg_1d"] - (837 / 830 - 1)) < 1e-6
    oko = by["OKOMUOIL"]
    assert oko["mcap"] == round(953_910_000_000.0 * 1.1, 2)                # scaled when shares are unknown
    quiet = by["QUIET"]                         # no close yet: the previous close, dated the trading day before
    assert quiet["price"] == 5.0 and quiet["date"] == "2026-11-05"


def test_previous_close_is_dated_the_trading_day_before():
    parsed = markets.parse_ngx_doclib([{"Symbol": "A", "ClosePrice": None, "PrevClosingPrice": 2.5,
                                        "TradeDate": "2026-11-09T00:00:00"}])          # a Monday
    assert parsed["A"]["price"] == 2.5 and parsed["A"]["date"] == "2026-11-06" and parsed["A"]["prev"] is None


def test_no_fallback_without_a_previous_list_or_for_exchanges_without_a_second_source():
    assert markets.fetch_exchange(markets.EXCHANGES["ngx"], _client(False), date(2026, 11, 6), None)[0] == []
    gse = [{"symbol": "MTNGH", "price": 3.0, "date": "2026-10-28"}]
    assert markets.fetch_exchange(markets.EXCHANGES["gse"], _client(False), date(2026, 11, 6), gse)[0] == []


def test_ytd_is_dropped_across_a_year_end():
    from src.engines import price_sources
    previous = [{"symbol": "X", "price": 10.0, "date": "2026-12-31", "ytd": 0.5},
                {"symbol": "Y", "price": 20.0, "date": "2026-12-31", "ytd": 0.1}]
    rows, verdict = price_sources.reprice(previous, {"X": {"price": 11.0, "date": "2027-01-02"},
                                                     "Y": {"price": 20.0, "date": "2027-01-02"}}, "test")
    assert verdict == "ok" and all("ytd" not in q for q in rows) and rows[0]["price"] == 11.0
