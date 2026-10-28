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
