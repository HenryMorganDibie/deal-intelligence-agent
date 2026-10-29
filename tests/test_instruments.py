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


SARB_ITEMS = [
    {"Name": "Treasury bills - 91 day (tender rates)", "Date": "2026-10-28", "Value": 7.16},
    {"Name": "Treasury bills - 364 day (tender rates)", "Date": "2026-10-28", "Value": 7.46},
    {"Name": "8.00% 2030 (R2030) (closing yields)", "Date": "2026-10-28", "Value": 8.035},
    {"Name": "SARB Policy Rate", "Date": "2026-10-29", "Value": 7.25},
]

BOG_PAGE = """<table><tr><th>Issue Date</th><th>Tender</th><th>Security Type</th><th>Discount Rate</th><th>Interest Rate</th></tr>
<tr><td>26 Oct 2026</td><td>2030</td><td>91 DAY BILL</td><td>4.5609</td><td>4.6135</td></tr>
<tr><td>19 Oct 2026</td><td>2029</td><td>91 DAY BILL</td><td>4.5707</td><td>4.6235</td></tr>
<tr><td>26 Oct 2026</td><td>2030</td><td>364 DAY BILL</td><td>8.8206</td><td>9.6739</td></tr></table>"""

BAM_PAGE = """<input name='date' type="text" value="02/11/2026"><table>
<tr><th>Maturités</th><th>Caractéristiques</th><th>Montant proposé</th><th>Min</th><th>Max</th><th>Montant adjugé</th><th>Limite</th><th>Moyen</th></tr>
<tr><td>26 semaines</td><td>03/05/2027,</td><td>1 830,00</td><td>2,23 %</td><td>2,30 %</td><td>1 700,00</td><td>2,28 %</td><td>2,26 %</td></tr>
<tr><td>2 ans</td><td>19/03/2029,2.55%</td><td>2 720,00</td><td>99,28 %</td><td>99,73 %</td><td>800,00</td><td>99,70 %</td><td>99,71 %</td></tr></table>"""

CBG_PAGE = """<p>to be issued on Wednesday October 28th, 2026, by the Central Bank</p><table>
<tr><th>Maturity Profiles</th><th>Floated</th><th>Applied</th><th>Accepted</th><th>Under</th><th>W.A Price</th><th>Yield P.A %</th><th>Low</th><th>High</th></tr>
<tr><td>91-Day T/Bills</td><td>15,000,000</td><td>11,240,000</td><td>11,240,000</td><td>-3,760,000</td><td>99.1000</td><td>3.6400</td><td>99.09</td><td>99.10</td></tr>
<tr><td>91-Day (SS)</td><td>5,000,000</td><td>20,445,000</td><td>5,000,000</td><td>15,445,000</td><td>99.2500</td><td>3.0300</td><td>99.25</td><td>99.25</td></tr></table>"""

BOT_DETAIL = {"TbillData": [["", "35 Days", "91 Days"], ["Weighted Average Price for Successful Bids", "99.6619", "99.1017"],
                            ["Weighted Average Yield", "3.5379", "3.6357"], ["Amount Offered TZS(000,000)", 49900, 69900]]}

BOZ_PAYLOAD = {"data": [{"attributes": {"title": "22/2026", "field_tbills_auction_date": "2026-10-29"}}],
               "included": [{"attributes": {"field_91_days_tenor": "91_days", "field_91_days_yield_rate": "8.5000",
                                            "field_91_discounted_rate": "8.3236"}}]}

UMOA_LIST = """<tr class='emission-sim'><td class="tb-emetteur-contenu"><img src="ci.png"/> Côte d’Ivoire<br><i>ES (Titre 1)</i></td><td>BAT</td><td class="tb-precisions"></td><td>27/10/2026</td><td>28/10/2026</td><td>26/10/2027</td><td>12</td><td>--</td><td class='all'><a href='https://umoa.example/ci-27' target='_blank'>Plus</a></td></tr>
<tr class='emission-sim'><td class="tb-emetteur-contenu"><img src="ci.png"/> Côte d’Ivoire<br><i>ES (Titre 2)</i></td><td>OAT</td><td class="tb-precisions"></td><td>27/10/2026</td><td>28/10/2026</td><td>26/10/2029</td><td>36</td><td>--</td><td class='all'><a href='https://umoa.example/ci-27' target='_blank'>Plus</a></td></tr>
<tr class='emission-sim'><td class="tb-emetteur-contenu"><img src="ci.png"/> Côte d’Ivoire<br><i>ES (Titre 1)</i></td><td>BAT</td><td class="tb-precisions"></td><td>20/10/2026</td><td>21/10/2026</td><td>19/10/2027</td><td>12</td><td>--</td><td class='all'><a href='https://umoa.example/ci-20' target='_blank'>Plus</a></td></tr>
<tr class='emission-sim'><td class="tb-emetteur-contenu"><img src="gw.png"/> Guinée Bissau<br><i>ES (Titre 1)</i></td><td>BAT</td><td class="tb-precisions"></td><td>19/10/2026</td><td>20/10/2026</td><td>11/10/2027</td><td>12</td><td>--</td><td class='all'><a href='https://umoa.example/gw-19' target='_blank'>Plus</a></td></tr>"""

UMOA_UNALLOTTED = """<h2>Résultats</h2><p>BAT | Montant sollicité: | 85 000 | Taux moyen pondéré: | -- % | Rendement moyen pondéré | -- %</p>
<p>OAT | Montant sollicité: | 85 000 | Prix moyen pondéré: | 9 688,44 F CFA | Rendement moyen pondéré | 6,3700 %</p>"""

UMOA_ALLOTTED = """<h2>Résultats</h2><p>BAT | Montant sollicité: | 40 000 | Taux moyen pondéré: | 3,7403 % | Taux marginal | 3,80 % |
Rendement moyen pondéré | 3,8900 %</p>"""


def test_south_africa_rates_kept_as_published_with_bond_yields():
    za = instruments.parse_sarb_rates(SARB_ITEMS)
    assert [(r["tenor_days"], r["rate"], r["rate_type"], r["basis"]) for r in za["rows"]] == [
        (91, 7.16, "tender", None), (364, 7.46, "tender", None)]     # convention not stated: never converted
    assert za["bonds"] == [{"name": "8.00% 2030 (R2030)", "yield": 8.035, "date": "2026-10-28"}]


def test_ghana_latest_tender_per_tenor_reconciles_on_364_days():
    gh = instruments.parse_bog_tbills(BOG_PAGE)
    r91 = gh["rows"][0]
    assert (r91["tenor_days"], r91["rate"], r91["discount_rate"], r91["auction_date"]) == (91, 4.6135, 4.5609, "2026-10-26")
    assert round(instruments.true_yield(r91["discount_rate"], 91, 364), 4) == 4.6135


def test_morocco_bills_only_with_settlement_date():
    ma = instruments.parse_bam_tbills(BAM_PAGE)
    assert [(r["tenor_label"], r["rate"], r["settlement_date"]) for r in ma["rows"]] == [("26 weeks", 2.26, "2026-11-02")]


def test_gambia_treasury_bills_not_sukuk():
    gm = instruments.parse_cbg_tbills(CBG_PAGE)
    assert [(r["tenor_days"], r["rate"], r["price"], r["auction_date"]) for r in gm["rows"]] == [(91, 3.64, 99.1, "2026-10-28")]


def test_seychelles_tanzania_and_zambia():
    sc = instruments.parse_cbs_tbills({"tbill": [{"date": "23 October, 2026", "rate1": "2.30", "rate2": "2.48", "rate3": "2.50"}]})
    assert [(r["tenor_days"], r["rate"], r["rate_type"]) for r in sc["rows"]][0] == (91, 2.3, "average")
    assert sc["rows"][0]["auction_date"] == "2026-10-23"
    tz = instruments.parse_bot_detail(BOT_DETAIL, "2026-10-21")
    assert [(r["tenor_days"], r["rate"], r["price"]) for r in tz["rows"]] == [(35, 3.5379, 99.6619), (91, 3.6357, 99.1017)]
    assert instruments.parse_bot_list("Treasury Bills Auction No. 1209  Held on 21-OCT-2026") == ("1209", "2026-10-21")
    zm = instruments.parse_boz_tbills(BOZ_PAYLOAD)
    assert [(r["tenor_days"], r["rate"], r["discount_rate"], r["auction_date"]) for r in zm["rows"]] == [(91, 8.5, 8.3236, "2026-10-29")]


def test_umoa_falls_back_to_the_last_auction_that_allotted_bills():
    listing = instruments.parse_umoa_list(UMOA_LIST)
    assert [a["date"] for a in listing["CI"]] == ["2026-10-27", "2026-10-20"] and "GW" in listing
    assert [i["kind"] for i in listing["CI"][0]["instruments"]] == ["BAT", "OAT"]
    assert instruments.parse_umoa_auction(UMOA_UNALLOTTED, listing["CI"][0])["rows"] == []   # '--' is no rate
    ci = instruments.parse_umoa_auction(UMOA_ALLOTTED, listing["CI"][1])
    assert ci["country_name"] == "Côte d'Ivoire" and ci["currency"] == "XOF"
    assert [(r["tenor_label"], r["rate"], r["true_yield"], r["basis"], r["auction_date"]) for r in ci["rows"]] == [
        ("12 months", 3.7403, 3.89, 360, "2026-10-20")]


def test_one_failing_source_does_not_stop_the_others(monkeypatch):
    class Resp:
        def __init__(self, text="", data=None, status=200):
            self.text, self._data, self.status_code = text, data, status

        def json(self):
            if self._data is None:
                raise ValueError("not json")
            return self._data

    pages = {instruments.BOG_TBILLS: Resp(BOG_PAGE), instruments.SARB_RATES: Resp(data=SARB_ITEMS)}
    monkeypatch.setattr(markets, "_get", lambda client, url, **kw: pages.get(url))   # every other source is down

    class Client:
        def post(self, *a, **k):
            raise RuntimeError("down")

    out = instruments.build_tbills(Client())
    assert sorted(out) == ["gh", "za"] and out["gh"]["country_name"] == "Ghana"
