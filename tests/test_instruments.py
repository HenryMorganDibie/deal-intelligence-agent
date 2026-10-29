"""ETFs, Treasury bill auctions, listed property and policy rates for the Markets investments page."""
from datetime import datetime, timezone

from src.engines import instruments, markets

CBN_ROWS = [
    {"auctionDate": "October-28-2026", "tenor": "91DAY", "rateDescription": "Issue", "rate": "15.4000",
     "maturityDate": "January-28-2027", "amtOffered": "100000.0000", "totalSubscription": "51556.3940",
     "totalSuccessful": "22331.6640", "rangeBid": "14.9000 - 19.0000"},
    {"auctionDate": "October-28-2026", "tenor": "364DAY", "rateDescription": "Issue", "rate": "15.8000",
     "maturityDate": "October-28-2027"},
    {"auctionDate": "October-14-2026", "tenor": "365Day", "rateDescription": "Issue", "rate": "15.9000",
     "maturityDate": "October-14-2027"},
    {"auctionDate": "October-28-2026", "tenor": "91DAY", "rateDescription": "Maginal", "rate": "19.0000"},
    {"auctionDate": "June-30-2021", "tenor": "182DAY", "rateDescription": "Issue", "rate": "3.5000"},
]

CBK_PAGE = """<h3>91-DAY</h3><p>Issue Number: 2706/91</p><p>Auction Date: 5th November 2026</p>
<p>Previous Average Interest Rate: 8.7498%</p><h3>182-DAY</h3><p>Auction Date: 5th November 2026</p>
<p>Previous Average Interest Rate: 8.8508 %</p><h3>364-DAY</h3><p>Auction Date: 5th November 2026</p>
<p>Previous Average Interest Rate: 9.0288</p>"""


def test_cbn_latest_auction_per_tenor_with_true_yield():
    ng = instruments.parse_cbn_ntb(CBN_ROWS)
    rows = {r["tenor_days"]: r for r in ng["rows"]}
    assert sorted(rows) == [91, 364]                       # 364 and 365-day bills are one tenor; 2021 is history
    assert rows[364]["rate"] == 15.8 and rows[364]["auction_date"] == "2026-10-28"
    assert rows[91]["rate"] == 15.4                         # the marginal rate is not the stop rate
    assert rows[91]["true_yield"] == 16.0149               # 15.4 / (1 - 0.154 * 91 / 365)
    assert rows[91]["allotted_mn"] == 22331.664 and rows[91]["bid_range"] == "14.9000 - 19.0000"


def test_true_yield_matches_cbn_published_figure():
    # CBN published 5.1517% for a 364-day bill at a 4.90% stop rate (29 Dec 2021).
    assert round(instruments.true_yield(4.9, 364), 3) == 5.152


def test_cbk_previous_average_rates():
    ke = instruments.parse_cbk_tbills(CBK_PAGE)
    assert [(r["tenor_days"], r["rate"]) for r in ke["rows"]] == [(91, 8.7498), (182, 8.8508), (364, 9.0288)]
    assert ke["rows"][0]["next_auction_date"] == "2026-11-05" and ke["rows"][0]["rate_type"] == "yield"


def test_etfs_by_exposure_and_unit_change_guard(monkeypatch):
    quotes = {"STX40.JO": {"price": 102.73, "chg_1d": 0.004, "ytd": -0.059, "date": "2026-10-29", "name": "Satrix 40 ETF"},
              "STXCAP.JO": {"price": 55.82, "ytd": 94.68, "date": "2026-10-29", "name": "Satrix Capped All Share ETF"},
              "GLD.JO": {"price": 616.85, "ytd": -0.072, "date": "2026-10-29", "name": "NewGold Issuer Limited"}}
    monkeypatch.setattr(markets, "_spark_all_range", lambda client, symbols, rng: quotes)
    etfs = instruments.build_etfs(None, now=datetime(2026, 10, 29, 12, tzinfo=timezone.utc))
    rows = {r["symbol"]: r for r in etfs["rows"]}
    assert set(rows) == {"STX40", "STXCAP", "GLD"}          # tickers with no quote drop out
    assert rows["STX40"]["exposure"] == "South African equity" and rows["GLD"]["exposure"] == "Precious metals"
    assert rows["STXCAP"]["ytd"] is None and rows["STXCAP"]["ytd_suspect"]


def test_listed_property_and_policy_rates():
    snap = {"quotes": {"jse": [{"symbol": "GRT", "name": "Growthpoint Properties", "sector": "Real Estate", "price": 15.0, "mcap_usd": 2e9},
                               {"symbol": "NRP", "name": "NEPI Rockcastle", "sector": "Real Estate", "price": 140.0, "mcap_usd": 5e9},
                               {"symbol": "MTN", "name": "MTN Group", "sector": "Telecom", "price": 150.0, "mcap_usd": 9e9}],
                       "ngx": [{"symbol": "NREIT", "name": "Nigeria Real Estate Investment Trust", "sector": "Financials", "price": 9.0}]}}
    assert [p["symbol"] for p in instruments.listed_property(snap)] == ["NRP", "GRT", "NREIT"]
    signals = {"countries": {"KE": {"country_name": "Kenya", "observations": [
        {"metric_key": "policy_rate_pct", "value": 9.25, "as_of_period": "2026-10-07", "source": "cbk"},
        {"metric_key": "fx_usd_daily", "value": 129.2}]}}}
    assert instruments.policy_rates(signals) == [{"country": "KE", "country_name": "Kenya", "rate": 9.25,
                                                  "as_of": "2026-10-07", "freshness": None, "source": "cbk"}]


def test_instruments_endpoint_serves_stored_blocks(monkeypatch):
    from fastapi.testclient import TestClient

    import api.index as api
    import src.hosted_market as hm

    monkeypatch.setattr(hm, "_configured", lambda: False)
    hm._markets_cache.clear()
    etfs = {"rows": [{"symbol": "STX40", "price": 102.73, "exposure": "South African equity"}], "delay": instruments.ETF_DELAY}
    ng = {**instruments.parse_cbn_ntb(CBN_ROWS), "captured_at": "2026-10-29T08:00:00+00:00"}
    instruments.save_local(instruments.instrument_rows(etfs, {"ng": ng}))
    body = TestClient(api.app).get("/api/markets/instruments").json()
    assert body["etfs"]["rows"][0]["symbol"] == "STX40"
    assert body["tbills"][0]["country"] == "NG" and len(body["tbills"][0]["rows"]) == 2
    assert isinstance(body["policy_rates"], list) and "not covered" in body["method"]
