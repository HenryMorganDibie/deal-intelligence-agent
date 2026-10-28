"""African equity markets: source parsers, staleness and plausibility guards, derived views and the endpoints."""
from datetime import date

from src.engines import markets

TODAY = date(2026, 10, 28)


def _row(cells: list[str], code: str = "") -> str:
    tds = "".join(f'<td class="tabcol">{c}</td>' for c in cells)
    if code:
        tds = tds.replace(f'<td class="tabcol">{cells[0]}</td>',
                          f"<td class=\"tabcol\"><a href='listed-companies/company?code={code}'>{cells[0]}</a></td>", 1)
    return f'<tr class="tabrow ">{tds}</tr>'


def _listing(head: list[str], rows: list[str]) -> str:
    th = "".join(f'<td class="tabcol">{h}</td>' for h in head)
    return (f'<table id="tab_abc" class="tabtable-rs_01k0jris "><thead><tr class="tabrow tr_ht1">{th}</tr> </thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


_INDEX_TABLE = (
    '<table id="tab_idx" class="tabtable-rs_m316x72x"><tbody>'
    "<tr class=\"tabrow \"><td class=\"tabcol\"><img src=\"/images/flags/ng.png\"/></td><td class=\"tabcol\"> "
    "<a href='/en/stock-markets/ngse' style='color: #ed5c28'>NGX ASI</a></td><td class=\"tabcol\">253,990.06</td>"
    "<td class=\"tabcol\"><font color=\"28a828\">+1.07%</font></td><td class=\"tabcol\">27/10</td></tr>"
    "</tbody></table>")


def test_listing_table_gives_price_returns_cap_and_shares():
    page = _listing(["Company", "Sector", "Price", "1D", "YTD", "M.Cap", "Date"], [
        _row(["Dangote Cement", "Industrials", "1,341.90", '<font color="28a828">+9.80%</font>', "+120.34%",
              "22642.62", "27/10"], "DANGCEM"),
        _row(["African Alliance Insurance", "Financials", "0.20", "-", "-", "4.11", "27/10"], "AFRINSURE"),
        _row(["SONATEL", "Telecom", "4,425", "-5.85%", "-83.06%", "4425", "27/10"], "SNTS"),
    ]) + _INDEX_TABLE
    quotes = markets.parse_listing(page, markets.EXCHANGES["ngx"], TODAY)
    dangote = quotes[0]
    assert dangote["symbol"] == "DANGCEM" and dangote["price"] == 1341.9
    assert dangote["chg_1d"] == 0.098 and dangote["ytd"] == 1.2034 and dangote["date"] == "2026-10-27"
    assert dangote["mcap"] == 22642.62e9 and round(dangote["shares"] / 1e9, 2) == 16.87
    assert quotes[1]["chg_1d"] is None and quotes[1]["ytd"] is None
    assert "mcap" not in quotes[2]                       # a cap equal to the price is a table glitch
    assert markets.parse_indices(page, TODAY) == [
        {"exchange": "ngx", "name": "NGX ASI", "level": 253990.06, "chg_1d": 0.0107, "date": "2026-10-27"}]


def test_egx_cap_column_is_shares_and_tunis_layout_has_a_symbol_column():
    egx = _listing(["Company", "Sector", "Price", "1D", "YTD", "M.Cap", "Date"], [
        _row(["Commercial International Bank (Egypt)", "Financials", "120.99", "+2.48%", "+17.47%", "3.4", "27/10"], "COMI")])
    cib = markets.parse_listing(egx, markets.EXCHANGES["egx"], TODAY)[0]
    assert cib["shares"] == 3.4e9 and round(cib["mcap"] / 1e9) == 411

    tunis = _listing(["Company", "Symbol", "Sector", "1D", "Change", "YTD", "Date"], [
        _row(["Air Liquide Tunisie", "AL", "Basic Materials", "179.01", "+0.01%", "+19.30%", "13/04"], "AL")])
    al = markets.parse_listing(tunis, markets.EXCHANGES["bvmt"], TODAY)[0]
    assert (al["price"], al["chg_1d"], al["ytd"], al["date"]) == (179.01, 0.0001, 0.193, "2026-04-13")
    assert "mcap" not in al


def test_a_day_month_after_today_belongs_to_last_year():
    assert markets._day_month("31/12", TODAY) == "2025-12-31"
    assert markets._day_month("27/10", TODAY) == "2026-10-27"


def test_mystocks_list_gives_signed_change_volume_sector_and_names():
    page = ("<title>Market Pricelist &amp;#8212; 27 Oct 2026 - myStocks Mobile</title>"
            "<option value=SCOM>Safaricom Plc</option><option value=BAT>British American Tobacco Kenya Plc</option>"
            "<tr class=row><th class=head colspan=4><h2>Manufacturing &amp; Allied</h2><tr class=\"row r1\">\n"
            '<td class=nm><a href="/m/stock=BAT">BAT</a><br>\n'
            '<td class=n>551.00<td class="n x-1">&#9660; 0.72%<td class=n>11,345<tr class=row>\n'
            "<th class=head colspan=4><h2>Telecommunication</h2><tr class=\"row r1\">\n"
            '<td class=nm><a href="/m/stock=SCOM">SCOM</a><br>\n'
            '<td class=n>33.25<td class="n x1">&#9650; 0.76%<td class=n>2.75M<tr class=row>')
    bat, scom = markets.parse_mystocks(page)
    assert bat == {"symbol": "BAT", "name": "British American Tobacco Kenya Plc", "sector": "Manufacturing & Allied",
                   "price": 551.0, "chg_1d": -0.0072, "volume": 11345.0, "date": "2026-10-27"}
    assert scom["chg_1d"] == 0.0076 and scom["volume"] == 2.75e6 and scom["sector"] == "Telecommunication"


def test_yahoo_spark_converts_cents_and_measures_year_to_date():
    payload = {"spark": {"result": [{"symbol": "MTN.JO", "response": [{
        "meta": {"currency": "ZAc", "regularMarketPrice": 19816.0, "regularMarketChangePercent": 0.533,
                 "regularMarketVolume": 3882587, "regularMarketTime": 1793113219, "longName": "MTN Group Limited"},
        "indicators": {"quote": [{"close": [15000.0, None, 19816.0]}]}}]}]}}
    q = markets.parse_spark(payload)["MTN.JO"]
    assert q["price"] == 198.16 and q["chg_1d"] == 0.00533 and round(q["ytd"], 4) == 0.3211


def _snapshot() -> dict:
    return {
        "quotes": {
            "ngx": [
                {"symbol": "DANGCEM", "name": "Dangote Cement", "sector": "Industrials", "price": 1341.9,
                 "chg_1d": 0.098, "ytd": 1.2, "mcap": 22.6e12, "date": "2026-10-27", "volume": 3e6},
                {"symbol": "MTNN", "name": "MTN Nigeria Communications", "sector": "Telecom", "price": 825.0,
                 "chg_1d": 0.0, "ytd": 0.61, "mcap": 17.3e12, "date": "2026-10-27"},
                {"symbol": "OLDCO", "name": "Old Co", "sector": "Industrials", "price": 2.0, "chg_1d": 0.5,
                 "ytd": 0.1, "mcap": 5e9, "date": "2026-07-31"},
            ],
            "nse": [{"symbol": "EQTY", "name": "Equity Group Holdings Plc", "sector": "Banking", "price": 60.0,
                     "chg_1d": 0.01, "volume": 1e6, "date": "2026-10-27"}],
            "rse": [{"symbol": "EQTY", "name": "Equity Group", "sector": "Financials", "price": 900.0, "chg_1d": 0.0,
                     "ytd": 0.8, "mcap": 3396e9, "date": "2026-10-27"}],
            "dse": [{"symbol": "NMB", "name": "NMB Bank Plc", "sector": "Financials", "price": 1880.0, "chg_1d": -0.02,
                     "ytd": -0.7765, "mcap": 9400e9, "date": "2026-10-27"}],
            "egx": [{"symbol": "ESRS", "name": "Ezz Steel", "sector": "Basic Materials", "price": 133.9,
                     "chg_1d": 0.01, "ytd": 0.16, "mcap": 9.7e15, "shares": 72.6e9, "date": "2026-10-27"}],
        },
        "indices": [{"exchange": "ngx", "name": "NGX ASI", "level": 253990.06, "chg_1d": 0.0107, "date": "2026-10-27"}],
        "fx": {"rates": {"NGN": 1350.0, "KES": 130.0, "RWF": 1480.0, "TZS": 2640.0, "EGP": 56.0},
               "jan1": {"NGN": 1450.0, "KES": 129.0, "RWF": 1458.0, "TZS": 2470.0, "EGP": 47.7}},
    }


def test_enrich_flags_stale_quotes_implausible_caps_suspect_returns_and_secondary_listings():
    rows = {(r["exchange"], r["symbol"]): r for r in markets.enrich(_snapshot(), TODAY)}
    assert rows[("ngx", "OLDCO")]["stale"] and not rows[("ngx", "DANGCEM")]["stale"]
    assert round(rows[("ngx", "DANGCEM")]["mcap_usd"] / 1e9, 2) == 16.74
    # Dollar YTD: the naira gained against the dollar, so the dollar return beats the local one.
    assert round(rows[("ngx", "DANGCEM")]["ytd_usd"], 4) == round(2.2 * 1450 / 1350 - 1, 4)
    assert rows[("egx", "ESRS")]["mcap_usd"] is None and rows[("egx", "ESRS")]["cap_note"]
    assert rows[("dse", "NMB")]["ytd_suspect"]
    assert rows[("rse", "EQTY")]["secondary_of"] == "nse" and "secondary_of" not in rows[("nse", "EQTY")]


def test_overview_excludes_stale_suspect_and_secondary_rows_from_returns_and_totals():
    o = markets.overview(_snapshot(), TODAY)
    tiles = {t["exchange"]: t for t in o["exchanges"]}
    ngx = tiles["ngx"]
    assert ngx["listed"] == 3 and ngx["priced_today"] == 2 and ngx["index"]["level"] == 253990.06
    assert ngx["advancers"] == 1 and ngx["decliners"] == 0
    # Cap-weighted over the two fresh shares only.
    expected = (22.6e12 + 17.3e12) / (22.6e12 / 2.2 + 17.3e12 / 1.61) - 1
    assert round(ngx["ytd_local"], 4) == round(expected, 4)
    assert tiles["rse"]["mcap_usd"] is None                 # Equity Group's cap is counted at home only
    assert tiles["dse"]["ytd_local"] is None                # the only share's YTD is flagged
    assert o["gainers"][0]["symbol"] == "DANGCEM"
    assert {g["symbol"] for g in o["gainers"]} == {"DANGCEM", "ESRS", "EQTY"}      # the stale OLDCO is left out
    assert o["most_traded"][0]["symbol"] == "DANGCEM"
    assert {c["currency"] for c in o["currencies"]} == {"NGN", "KES", "RWF", "TZS", "EGP"}


def test_search_and_resolve_prefer_exact_names_and_symbols():
    snap = _snapshot()
    snap["quotes"]["gse"] = [{"symbol": "MTNGH", "name": "MTN Ghana", "price": 6.5, "date": "2026-10-27"}]
    snap["quotes"]["jse"] = [{"symbol": "MTN", "name": "MTN Group", "price": 198.0, "date": "2026-10-27"}]
    assert markets.resolve(snap, "MTN Group", today=TODAY)["exchange"] == "jse"
    assert markets.resolve(snap, "MTN Ghana", today=TODAY)["symbol"] == "MTNGH"
    assert markets.resolve(snap, "Dangote Cement Plc", today=TODAY)["symbol"] == "DANGCEM"
    assert markets.resolve(snap, "DANGCEM.LG", today=TODAY)["symbol"] == "DANGCEM"
    assert markets.resolve(snap, "Flutterwave", today=TODAY) is None
    assert markets.quote(snap, "nse", "eqty", today=TODAY)["price"] == 60.0


def test_screener_filters_by_exchange_sector_and_cap():
    snap = _snapshot()
    out = markets.screener(snap, sector="Financials", today=TODAY)
    assert {r["symbol"] for r in out["rows"]} == {"EQTY", "NMB"}    # "Banking" maps to Financials
    big = markets.screener(snap, min_mcap_usd=10e9, today=TODAY)
    assert [r["symbol"] for r in big["rows"]] == ["DANGCEM", "MTNN"]
    assert markets.screener(snap, exchange="ngx", include_stale=True, today=TODAY)["total"] == 3


def test_snapshot_rows_round_trip_through_storage_shape():
    snap = _snapshot()
    snap["errors"] = []
    rows = markets.snapshot_rows(snap)
    assert {(r["kind"], r["scope"]) for r in rows} >= {("quotes", "ngx"), ("indices", "all"), ("fx", "usd")}
    back = markets.from_rows([r for r in rows if r["kind"] == "quotes"], [r for r in rows if r["kind"] == "indices"],
                             [r for r in rows if r["kind"] == "fx"])
    assert back["quotes"]["ngx"] == snap["quotes"]["ngx"] and back["fx"]["rates"]["NGN"] == 1350.0


def test_market_endpoints_serve_the_stored_snapshot(monkeypatch):
    from fastapi.testclient import TestClient

    import api.index as api
    import src.hosted_market as hm

    monkeypatch.setattr(hm, "_configured", lambda: False)
    hm._markets_cache.clear()
    snap = _snapshot()
    snap["errors"] = []
    markets.save_local(snap)
    client = TestClient(api.app)
    overview = client.get("/api/markets/overview").json()
    assert overview["coverage"]["shares"] == 7
    assert client.get("/api/markets/search", params={"q": "dangote"}).json()["results"][0]["symbol"] == "DANGCEM"
    assert client.get("/api/markets/quote", params={"exchange": "ngx", "symbol": "MTNN"}).json()["price"] == 825.0
    assert client.get("/api/markets/quote", params={"exchange": "ngx", "symbol": "NOPE"}).status_code == 404
    assert client.get("/api/markets/screener", params={"sort": "chg_1d", "include_stale": True}).json()["total"] == 7
    assert client.get("/api/cron/market-snapshot").status_code == 401


def test_profile_takes_the_snapshot_quote_and_withholds_multiples_on_a_stale_price(monkeypatch):
    from datetime import datetime, timezone

    from src.engines import company_profile

    rows = {(r["exchange"], r["symbol"]): r for r in markets.enrich(_snapshot(), TODAY)}
    now = datetime(2026, 10, 28, tzinfo=timezone.utc)
    # NGX's trading summary lagged the price list (Dangote at 1066.7 when the list said 1341.9).
    monkeypatch.setattr(company_profile, "_ngx_section", lambda ticker, fetch=None: {
        "identity": {"name": "Dangote Cement Plc"},
        "market": {"price": 1066.7, "as_at": "2026-10-13", "currency": "NGN"}, "multiples": {"trailingPE": 9.0}})
    p = company_profile.build("Dangote Cement", listing=rows[("ngx", "DANGCEM")], today=now)
    assert p["ticker"] == "DANGCEM.LG" and p["market"]["price"] == 1341.9 and p["market"]["as_at"] == "2026-10-27"
    assert round(p["market"]["market_cap_usd"] / 1e9, 2) == 16.74 and not p["market"]["stale"]
    assert p["multiples"] == {"trailingPE": 9.0} and "Private company" not in (p.get("financials_note") or "")

    # A listing whose latest price is weeks old keeps its price (the newer of the two sources), flagged.
    p = company_profile.build("Old Co", listing={**rows[("ngx", "OLDCO")]}, today=now)
    assert p["market"]["price"] == 1066.7 and p["market"]["stale"] and p["market"]["age_days"] == 15
    monkeypatch.setattr(company_profile, "_ngx_section", lambda ticker, fetch=None: {
        "market": {"price": 5.0, "as_at": "2026-07-01", "currency": "NGN"}, "multiples": {"trailingPE": 4.0}})
    p = company_profile.build("Old Co", ticker="OLDCO.LG", today=now)
    assert p["multiples"] == {} and "days old" in p["multiples_withheld"]


def test_profile_route_resolves_a_name_to_its_listing(monkeypatch):
    from fastapi.testclient import TestClient

    import api.index as api
    import src.hosted_market as hm
    from src.engines import company_profile

    monkeypatch.setattr(hm, "_configured", lambda: False)
    hm._markets_cache.clear()
    hm._profile_cache.clear()
    snap = _snapshot()
    snap["quotes"]["gse"] = [{"symbol": "MTNGH", "name": "MTN Ghana", "price": 6.53, "chg_1d": 0.0062,
                              "mcap": 80.25e9, "date": date.today().isoformat()}]
    snap["fx"]["rates"]["GHS"] = 11.64
    markets.save_local(snap)
    monkeypatch.setattr(company_profile, "_yahoo_section", lambda ticker: None)
    p = TestClient(api.app).get("/api/companies/profile", params={"name": "MTN Ghana"}).json()
    assert p["listing"]["symbol"] == "MTNGH" and p["exchange"] == "Ghana Stock Exchange"
    assert p["market"]["price"] == 6.53 and p["valuation"]["market_cap"] == 80.25e9
    assert p["country"] == "GH"


def test_a_throttled_listing_page_is_retried(monkeypatch):
    import httpx

    monkeypatch.setattr(markets.time, "sleep", lambda s: None)
    page = _listing(["Company", "Sector", "Price", "1D", "YTD", "M.Cap", "Date"], [
        _row(["MTN Ghana", "Telecom", "6.53", "+0.62%", "+55.48%", "80.25", "27/10"], "MTNGH")])
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(429) if len(calls) == 1 else httpx.Response(200, text=page)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        quotes, _ = markets.fetch_exchange(markets.EXCHANGES["gse"], client, TODAY)
    assert len(calls) == 2 and quotes[0]["symbol"] == "MTNGH"


def test_prices_endpoint_prices_holdings_by_ticker_or_name_and_returns_fx(monkeypatch):
    from fastapi.testclient import TestClient

    import api.index as api
    import src.hosted_market as hm

    monkeypatch.setattr(hm, "_configured", lambda: False)
    hm._markets_cache.clear()
    markets.save_local(_snapshot())
    out = TestClient(api.app).post("/api/markets/prices", json={"items": [
        {"ticker": "DANGCEM.LG"}, {"name": "Equity Group Holdings", "country": "Kenya"},
        {"name": "MTN Nigeria Communications", "currency": "USD"}, {"name": "Flutterwave"}]}).json()
    first, eqty, wrong_ccy, private = out["results"]
    assert first["price"] == 1341.9 and first["currency"] == "NGN"
    assert eqty["exchange"] == "nse"
    assert wrong_ccy is None and private is None
    assert out["fx"]["usd_rates"]["NGN"] == 1350.0 and out["fx"]["usd_rates"]["USD"] == 1.0


def test_events_carry_their_measured_track_record(monkeypatch):
    from fastapi.testclient import TestClient

    import api.index as api
    import src.hosted_market as hm
    from src.engines import measured

    monkeypatch.setattr(hm, "_configured", lambda: False)
    hm._measures_cache.clear()
    monkeypatch.setattr(hm, "events", lambda: [
        {"id": "e1", "day": "2026-10-27", "signal_type": "m_and_a_activity", "headline": "Dangote buys stake", "country": "NG"}])
    monkeypatch.setattr(measured, "track_record", lambda t, sev, sub, market: {
        "grade": "proven", "label": "Proven: 1.8x", "lift": 1.8, "n": 300, "basis": "b", "graded_on": "African",
        "market": market})
    monkeypatch.setattr(measured, "expected_move", lambda t, sev: {"median": 0.3, "p25": -2.9, "p75": 3.6, "n": 2000,
                                                                    "share_negative": 0.47, "basis": "x"})
    e = TestClient(api.app).get("/api/events").json()["events"][0]
    assert e["measured"]["grade"] == "proven" and e["measured"]["move_10d"]["median"] == 0.3


def test_cost_of_equity_builds_up_from_risk_score_and_inflation(monkeypatch):
    from src.data import africa_countries as ac
    from src.engines import country_risk, market_risk

    monkeypatch.setattr(country_risk, "assess", lambda c, fx=None: {
        "score": 47.0, "tier": "elevated", "indicators": {"FP.CPI.TOTL.ZG": {"value": 23.0, "year": 2025}}})
    r = market_risk.cost_of_equity(ac.get("NG"))
    assert r["country_premium"] == 0.08 and r["cost_of_equity_usd"] == round(0.043 + 0.045 + 0.08, 4)
    assert r["cost_of_equity_local"] == round(1.168 * 1.23 / 1.027 - 1, 4) and r["currency"] == "NGN"


def test_valuation_bridge_places_a_private_mark_among_listed_peers():
    snap = _snapshot()
    banks = [{"symbol": f"B{i}", "name": f"Bank {i}", "sector": "Banking", "price": 10.0, "chg_1d": 0.0, "ytd": 0.1,
              "mcap": cap * 1350.0, "date": "2026-10-27"} for i, cap in enumerate([2e8, 5e8, 9e8, 1.5e9, 3e9, 6e9])]
    snap["quotes"]["ngx"] = snap["quotes"]["ngx"] + banks
    b = markets.valuation_bridge(snap, 1e9, "fintech", "NG", "2024-10-30", today=TODAY)
    assert b["sector"] == "Financials" and b["scope"] == "country" and b["peers"] == 6
    assert b["larger_than"] == 3 and b["rank_percentile"] == 0.5
    assert b["largest_peers"][0]["symbol"] == "B5"
    assert markets.valuation_bridge(snap, 1e9, "hospitality", "NG", today=TODAY) is None     # too few peers
    assert markets.valuation_bridge(snap, None, "fintech", "NG", today=TODAY) is None


def test_yahoo_screen_rows_recompute_multiples_in_one_unit():
    row = {"currency": "ZAc", "financialCurrency": "ZAR", "regularMarketPrice": 19816.0, "sharesOutstanding": 1.88e9,
           "epsTrailingTwelveMonths": 9.91, "bookValue": 66.0, "dividendYield": 3.1, "regularMarketChangePercent": 0.5,
           "regularMarketTime": 1793113219, "longName": "MTN Group Limited"}
    q = markets.parse_screen_row(row)
    assert q["price"] == 198.16 and q["mcap"] == round(198.16 * 1.88e9, 2)
    assert q["pe"] == 20.0 and q["pb"] == 3.0 and q["dividend_yield"] == 0.031
    assert markets.parse_screen_row({**row, "epsTrailingTwelveMonths": 0.5})["pe"] is None      # 396x: not kept


def test_uganda_feed_and_ethiopia_directory_parse():
    feed = [{"type": "EQUITY", "stock": "MTNU", "price": 455, "market_cap": 10187015128745, "volume": 100},
            {"type": "EQUITY", "stock": "FXD 2/2015/15", "price": 139.3, "market_cap": 1}]
    page = "<table><tr><th>Counter</th><th>ISIN</th><th>Full Name</th></tr><tr><td>MTNU</td><td>UG1</td><td>MTN Uganda</td></tr></table>"
    (mtn,) = markets.parse_use(feed, page, date(2026, 10, 31))           # a Saturday capture is Friday's close
    assert mtn["name"] == "MTN Uganda" and mtn["date"] == "2026-10-30" and mtn["shares"] == round(10187015128745 / 455)
    esx = ("<table><tr><th>Name</th><th>Symbol</th><th>Sector</th><th>Date Listed</th></tr>"
           "<tr><td>Ethio Telecom Share Company</td><td>TELE</td><td>Telecom Servicess</td><td>2026-05-26</td></tr></table>")
    (tele,) = markets.parse_esx(esx)
    assert tele["price"] is None and tele["sector"] == "Telecom Services"
    snap = _snapshot()
    snap["quotes"]["esx"] = [tele]
    rows = {r["symbol"]: r for r in markets.enrich(snap, TODAY)}
    assert rows["TELE"]["stale"] and markets.resolve(snap, "Ethio Telecom", today=TODAY)["exchange"] == "esx"
    assert markets.overview(snap, TODAY)["coverage"]["shares"] == 8


def test_daily_change_is_filled_from_the_previous_close():
    prev = {"quotes": {"use": [{"symbol": "MTNU", "price": 450.0, "date": "2026-10-27"}]}}
    now = {"quotes": {"use": [{"symbol": "MTNU", "price": 459.0, "date": "2026-10-28", "chg_1d": None}]}}
    assert markets.fill_daily_change(now, prev) == 1 and now["quotes"]["use"][0]["chg_1d"] == 0.02


def test_directory_merges_listed_and_private_companies():
    from src.engines import company_directory as cd

    deals = [
        {"id": "1", "deal_type": "equity_funding", "target": "Moniepoint", "country": "NG", "sector": "fintech",
         "amount_usd": 110e6, "round": "series c", "announced": "2024-10-29", "investors": ["Development Partners International"],
         "reported_valuation_usd": 1e9},
        {"id": "2", "deal_type": "debt_financing", "target": "Moniepoint", "country": "NG", "sector": "fintech",
         "amount_usd": 20e6, "announced": "2025-03-01", "buyer": "IFC"},
        {"id": "3", "deal_type": "acquisition", "target": "Dangote Cement Plc", "country": "NG", "sector": "manufacturing",
         "buyer": "Dangote Industries", "stake_pct": 5, "announced": "2026-01-10"},
        {"id": "4", "deal_type": "equity_funding", "target": "Undisclosed fintech", "country": "KE", "amount_usd": 1e6},
    ]
    rows = cd.directory(_snapshot(), deals, today=TODAY)
    private = {r["name"]: r for r in rows if r["kind"] == "private" and not r.get("source")}
    assert set(private) == {"Moniepoint"}
    m = private["Moniepoint"]
    assert m["equity_raised_usd"] == 110e6 and m["debt_raised_usd"] == 20e6 and m["deal_count"] == 2
    assert m["valuation_usd"] == 1e9 and m["sector"] == "Financials" and "International Finance Corporation" in m["investors"]
    dangote = next(r for r in rows if r.get("symbol") == "DANGCEM")
    assert dangote["kind"] == "listed" and dangote["deal_count"] == 1          # its deal history folds into the listing
    out = cd.query(rows, q="moniepoint")
    assert out["rows"][0]["name"] == "Moniepoint" and out["counts"] == {"listed": 0, "private": 1}
    assert "Dangote Cement" not in {r["name"] for r in rows if r.get("source")}     # curated, but already listed


def test_directory_adds_companies_known_only_from_events_and_the_curated_list():
    from src.engines import company_directory as cd

    events = [{"headline": "Kakuzi Plc issues profit warning", "country": "KE", "day": "2026-10-20"},
              {"headline": "Kakuzi Plc board names new chairman", "country": "KE", "day": "2026-10-25"},
              {"headline": "Inflation rises in Kenya", "country": "KE", "day": "2026-10-25"}]
    rows = cd.directory(_snapshot(), [], today=TODAY, events=events)
    kakuzi = next(r for r in rows if r["name"] == "Kakuzi")
    assert kakuzi["event_count"] == 2 and kakuzi["last_event_date"] == "2026-10-25" and kakuzi["source"] == "corporate events"
    assert any(r.get("source") == "curated list" for r in rows)


def test_jse_keeps_the_last_screened_list_when_the_screener_is_rate_limited(monkeypatch):
    import httpx

    monkeypatch.setattr(markets, "yahoo_screen", lambda exchange, attempts=3: {})
    spark = {"spark": {"result": [{"symbol": "NPN.JO", "response": [{"meta": {
        "currency": "ZAc", "regularMarketPrice": 400000.0, "regularMarketChangePercent": 1.0,
        "regularMarketTime": 1793113219}, "indicators": {"quote": [{"close": [350000.0]}]}}]}]}}
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=spark))) as client:
        quotes = markets._jse_quotes("", client, previous=[
            {"symbol": "NPN", "name": "Naspers", "sector": "Technology", "price": 3800.0, "shares": 1.6e8, "pe": 19.0}])
    (npn,) = quotes
    assert npn["name"] == "Naspers" and npn["price"] == 4000.0 and npn["mcap"] == 4000.0 * 1.6e8
    assert npn["pe"] == 20.0                                # repriced with the share price


def test_directory_folds_described_names_and_drops_placeholder_investors():
    from src.engines import company_directory as cd

    deals = [
        {"id": "1", "deal_type": "equity_funding", "target": "Moniepoint", "country": "NG", "amount_usd": 110e6,
         "announced": "2024-10-29", "investors": ["Visa"]},
        {"id": "2", "deal_type": "equity_funding", "target": "Billion-Dollar Fintech Moniepoint", "country": "NG",
         "amount_usd": 90e6, "announced": "2025-06-01", "investors": ["Google", "And Others"]},
    ]
    (m,) = cd.private_companies(deals)
    assert m["name"] == "Moniepoint" and m["deal_count"] == 2 and m["equity_raised_usd"] == 200e6
    assert "And Others" not in m["investors"] and {"Visa", "Google"} <= set(m["investors"])


def test_new_exchange_parsers():
    vfex = markets.parse_vfex(
        {"data": [{"name": "INNSCOR AFRICA LIMITED", "closePrice": 1.5089, "percentageChange": 7.55, "turnover": 10,
                   "turnoverValue": 15.1, "statsDate": [2026, 10, 27]},
                  {"name": "FIRST MUTUAL WEALTH GOLD EXCHANGE TRADED FUND", "closePrice": 0.11, "statsDate": [2026, 10, 27]}]},
        {"data": [{"companyName": "INNSCOR AFRICA LIMITED", "symbol": "INN.VX", "outstandingShares": 5.7e8}]})
    assert [(q["symbol"], q["chg_1d"], q["date"], q["mcap"]) for q in vfex] == [("INN", 0.0755, "2026-10-27", round(1.5089 * 5.7e8, 2))]

    action = ('<table><tr><th>N° Code</th></tr><tr><th>GA0000010074</th><td>BGFI HC</td><td>2026-05-18</td><td>2500</td>'
              '<td></td><td>89 000</td><td>89 000</td><td>21</td><td>683</td><td>21</td><td>1,5</td><td>PEq</td></tr></table>')
    (bgfi,) = markets.parse_bvmac({"action": action, "datecapitalisation": "SEANCE DE COTATION : Mardi 27 Octobre 2026"})
    assert (bgfi["country"], bgfi["price"], bgfi["date"]) == ("GA", 89000.0, "2026-10-27")

    home = "Séance du Mardi : 27 Octobre 2026 ALL 360,00 1,41 AL30 100,00 0,00 ALL 355,00 3,60"
    companies = ("<table><tr><td>DZ0000010037</td><td>ALL</td><td>ALLIANCE ASSURANCES</td><td>ASSURANCE</td>"
                 "<td>380</td><td>13 930 826</td></tr></table>")
    (alliance,) = markets.parse_sgbv(home, companies)
    assert (alliance["price"], alliance["chg_1d"], alliance["shares"]) == (360.0, 0.0141, 13930826.0)

    ese = markets.parse_ese("LATEST PRICES FNBE : E14.83/share GRYS : E3.00/share LATEST NEWS", TODAY)
    assert [(q["symbol"], q["name"], q["price"]) for q in ese] == [("FNBE", "First National Bank Eswatini", 14.83),
                                                                  ("GRYS", "GRYS", 3.0)]

    merj = markets.parse_merj({"data": [{"ticker": "CWS", "current_price": 400, "change_percent": 0, "last_close": "2026-10-27 23:59:59"},
                                        {"ticker": "AAPL.iob", "current_price": 347.1}]},
                              {"data": [{"ticker": "CWS", "company_name": "Cable & Wireless Seychelles"}]})
    assert [(q["symbol"], q["name"], q["date"]) for q in merj] == [("CWS", "Cable & Wireless Seychelles", "2026-10-27")]

    board = markets.parse_ilboursa('<tr><td><a href="cotation_AL">AL</a></td><td>1</td><td>1</td><td>1</td>'
                                   '<td>2</td><td>462</td><td><b>230.99</b></td><td>-0.50%</td></tr>', TODAY)
    assert board["AL"]["price"] == 230.99 and board["AL"]["chg_1d"] == -0.005


def test_bodiva_codes_and_namibia_dual_listings():
    import io
    import zipfile

    strings = ["Resumo dos Mercados - 28/10/2026 08:46:44", "Acções", "BFAAAAAA", "BCGAAAAA"]
    sst = "<sst>" + "".join(f"<si><t>{x}</t></si>" for x in strings) + "</sst>"
    def c(v, s=False):
        return f'<c r="A1" t="s"><v>{v}</v></c>' if s else f'<c r="A1"><v>{v}</v></c>'
    sheet = ("<worksheet><sheetData><row>" + c(0, True) + "</row>"
             "<row>" + c(2, True) + c(1, True) + c(98500) + c(-0.015) + c(3) + c(10) + c(985000) + "</row>"
             "<row>" + c(3, True) + c(1, True) + c(19749) + c(0.034) + c(1) + c(1) + c(19749) + "</row></sheetData></worksheet>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", sst)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    quotes = markets.parse_bodiva(buf.getvalue())
    assert [(q["symbol"], q["name"], q["date"]) for q in quotes] == [
        ("BFA", "Banco de Fomento Angola", "2026-10-28"), ("BCGA", "Banco Caixa Geral Angola", "2026-10-28")]

    snap = {"nsx": [{"symbol": "ANM", "name": "Anglo American plc", "price": 500.0, "date": "2026-07-31"}],
            "jse": [{"symbol": "AGL", "name": "Anglo American", "price": 580.0, "chg_1d": 0.01, "date": "2026-10-27"}]}
    markets._price_from_dual_listing(snap, "nsx", "jse")
    assert snap["nsx"][0]["price"] == 580.0 and snap["nsx"][0]["priced_from"] == "jse"


def test_jse_groups_listed_primarily_abroad_keep_their_cap_outside_totals():
    snap = {"quotes": {"jse": [
        {"symbol": "BHG", "name": "BHP Group", "price": 500.0, "mcap": 2.5e12, "chg_1d": 0.0, "ytd": 0.1, "date": "2026-10-27"},
        {"symbol": "CPI", "name": "Capitec", "price": 3600.0, "mcap": 4e11, "chg_1d": 0.0, "ytd": 0.2, "date": "2026-10-27"}]},
        "indices": [], "fx": {"rates": {"ZAR": 16.6}, "jan1": {"ZAR": 16.5}}}
    rows = {r["symbol"]: r for r in markets.enrich(snap, TODAY)}
    assert rows["BHG"]["foreign_primary"] and rows["BHG"]["mcap_usd"] > 1e11
    tile = next(t for t in markets.overview(snap, TODAY)["exchanges"] if t["exchange"] == "jse")
    assert round(tile["mcap_usd"]) == round(4e11 / 16.6, -0) or abs(tile["mcap_usd"] - 4e11 / 16.6) < 1
