from datetime import date

from src.engines import content_drafts as cd
from src.engines import market_briefing as mb

TODAY = date(2026, 11, 11)
OV = {
    "exchanges": [
        {"exchange": "jse", "name": "Johannesburg Stock Exchange", "country": "ZA", "as_of": "2026-11-10", "mcap_usd": 5.9e11,
         "ytd_usd": 0.021, "advancers": 301, "decliners": 178, "index": {"name": "JSE ASI", "chg_1d": -0.001, "date": "2026-10-28"}},
        {"exchange": "bodiva", "name": "BODIVA (Angola)", "country": "AO", "as_of": "2026-11-10", "advancers": 3, "decliners": 3},
        {"exchange": "esx", "name": "Eswatini Stock Exchange", "country": "SZ", "as_of": "2026-11-10", "advancers": 0, "decliners": 0},
        {"exchange": "old", "name": "Old Exchange", "country": "ET", "as_of": "2026-09-01", "ytd_usd": 0.1},
    ],
    "gainers": [{"name": "Delta", "exchange": "jse", "chg_1d": 0.2}, {"name": "Thin Co", "exchange": "jse", "chg_1d": 0.45}],
    "losers": [{"name": "SAFACAM", "exchange": "jse", "chg_1d": -1.3}, {"name": "Montauk", "exchange": "jse", "chg_1d": -0.37},
               {"name": "Gold Fields", "exchange": "jse", "chg_1d": -0.044}],
    "most_traded": [{"name": "Naspers", "exchange": "jse", "value_traded_usd": 1.03e8, "chg_1d": 0.014}],
    "sectors": [{"sector": "Oil & Gas", "shares": 26, "mcap_usd": 1.85e10, "ytd_usd": 0.709, "chg_1d": -0.002},
                {"sector": "Basic Materials", "shares": 42, "mcap_usd": 1.1e10, "ytd_usd": -0.0001, "chg_1d": 0}],
    "currencies": [{"currency": c, "per_usd": p, "ytd_vs_usd": y} for c, p, y in
                   (("ZMW", 22.0, 0.093), ("NGN", 1349.07, 0.072), ("NAD", 18.0, 0.007), ("EGP", 54.07, -0.118),
                    ("GHS", 11.7, -0.103), ("UGX", 3700, -0.098))],
}
INST = {"tbills": [{"country_name": "Kenya", "rows": [{"tenor_label": "91 days", "tenor_days": 91, "rate": 8.75, "auction_date": "2026-11-05"}]},
                   {"country_name": "Nigeria", "rows": [{"tenor_label": "91 days", "tenor_days": 91, "rate": 16.01, "auction_date": "2026-11-04"}]},
                   {"country_name": "Benin", "rows": [{"tenor_label": "3 months", "tenor_days": 91, "rate": 3.2, "auction_date": "2026-06-11"}]}],
        "policy_rates": [{"country_name": "Nigeria", "rate": 23, "date": "2026-11-06", "confirmed_by": "central bank"}],
        "etfs": {"rows": [{"name": "Satrix 40", "chg_1d": -0.006}, {"name": "Meristem Value", "chg_1d": 0.083}]}}
EVENTS = [{"day": "2026-11-11", "headline": "MTN pushes IHS takeover", "country": "NG", "publisher": "BI Africa", "credibility": 0.8},
          {"day": "2026-11-11", "headline": "How to buy SpaceX stock", "country": "ZA", "credibility": 0.4}]


def test_briefing_covers_every_market_and_keeps_bad_prices_out():
    b = mb.build(OV, INST, EVENTS, TODAY)
    sec = {s["title"]: s["lines"] for s in b["sections"]}
    assert {"Exchanges", "Top gainers", "Top losers", "Check before using", "Most traded", "Sectors", "Currencies",
            "Treasury bills", "Policy rates", "ETFs", "Company news (last 24 hours)"} <= set(sec)
    ex = " | ".join(sec["Exchanges"])
    assert "BODIVA (Angola):" in ex and "(Angola) (Angola)" not in ex
    assert "Eswatini" not in ex and "Old Exchange" not in ex and "JSE ASI" not in ex     # stale index left out
    assert any("SAFACAM" in l for l in sec["Check before using"]) and not any("SAFACAM" in l for l in sec["Top losers"])
    assert "Basic Materials: 0% this year" in " ".join(sec["Sectors"])
    assert sec["Treasury bills"][0].startswith("Kenya (new this week)") and "Benin:" in sec["Treasury bills"][-1]
    assert sec["Company news (last 24 hours)"] == ["MTN pushes IHS takeover (Nigeria, BI Africa)"]


def test_market_posts_fit_on_x_and_skip_thin_trading_swings():
    b = mb.build(OV, INST, EVENTS, TODAY)
    kinds = {d["kind"]: d for d in b["drafts"]}
    assert {"Stock movers", "Currencies", "Treasury bills"} <= set(kinds)
    assert "Montauk" not in kinds["Stock movers"]["x"] and "Thin Co" not in kinds["Stock movers"]["x"]
    assert all(cd.x_length(d["x"]) <= cd.X_LIMIT for d in b["drafts"] if d.get("x"))


def test_email_carries_the_briefing():
    res = cd.build([], TODAY, OV, mb.build(OV, INST, EVENTS, TODAY))
    subject, body, text = cd.render_email(res)
    assert "market briefing" in subject.lower() and "Market briefing" in body and "Treasury bills" in text


def test_every_post_links_to_its_own_dated_page():
    b = mb.build(OV, INST, EVENTS, TODAY)
    links = {d["kind"]: d["x"].rsplit(" ", 1)[-1].split("\n")[-1] for d in b["drafts"]}
    assert links["Stock movers"].endswith("/markets/movers/2026-11-11")
    assert links["Currencies"].endswith("/markets/currencies/2026-11-11")
    assert links["Treasury bills"].endswith("/markets/treasury-bills/2026-11-11")
    res = cd.build([], TODAY, OV, None)
    market = next(d for d in res["drafts"] if d["kind"] == "Markets")
    assert market["x"].endswith("/markets/sectors/2026-11-11")
    assert links["Election watch"].endswith("/markets/election/2026-11-11")
    assert len(set(links.values()) | {market["x"].split()[-1]}) == 5


def test_dated_deal_windows_carry_the_email_checks(monkeypatch):
    from fastapi.testclient import TestClient
    import api.index as api
    from src import hosted_market as hm
    rows = [{"id": "a", "target": "Alpha", "deal_type": "equity_funding", "announced": "2026-11-10", "amount_usd": 5e6,
             "country": "NG", "sources": [{"url": "https://a"}], "headline": "Alpha raises $5m"}]
    monkeypatch.setattr(hm, "deals", lambda: rows)
    monkeypatch.setattr(hm, "_behavioral_interest_scores", lambda: {})
    monkeypatch.setenv("DEAL_INTEL_API_SECRET", "s")
    client = TestClient(api.app)
    h = {"x-deal-intel-client": "s"}
    windowed = client.get("/api/deals?since=2026-11-09&until=2026-11-11", headers=h).json()["deals"][0]
    plain = client.get("/api/deals", headers=h).json()["deals"][0]
    assert "review_flags" in windowed and "review_flags" not in plain


def _with_ngx():
    ov = {**OV, "exchanges": OV["exchanges"] + [{"exchange": "ngx", "name": "Nigerian Exchange", "country": "NG",
                                                "as_of": "2026-11-10", "ytd_local": 0.412, "ytd_usd": 0.51}]}
    inst = {**INST, "tbills": [{**b, "country": "NG"} if b["country_name"] == "Nigeria" else b for b in INST["tbills"]]}
    return ov, inst


def test_election_countdown_window_and_wording():
    assert mb.election(date(2026, 9, 1)) is None                     # more than four months out
    assert mb.election(date(2026, 11, 12))["hook"] == "65 days to Nigeria's general election"
    assert mb.election(date(2027, 1, 15))["hook"] == "Nigeria's general election is tomorrow"
    assert mb.election(date(2027, 1, 16))["countdown"] == "polling day"
    assert mb.election(date(2027, 1, 20))["hook"] == "4 days after Nigeria's general election"
    assert mb.election(date(2027, 2, 20)) is None                    # a month after, the angle is gone


def test_election_angle_in_posts_and_briefing():
    ov, inst = _with_ngx()
    b = mb.build(ov, inst, EVENTS, date(2026, 11, 10))
    assert b["sections"][0]["title"].startswith("Election watch: 67 days to Nigeria's general election")
    lines = " | ".join(b["sections"][0]["lines"])
    assert "up 7.2% against the dollar" in lines and "NGX: +41.2% this year" in lines and "91-day T-bill: 16.01%" in lines
    drafts = {d["kind"]: d for d in b["drafts"]}
    assert b["drafts"][0]["kind"] == "Election watch"
    assert "/markets/election/2026-11-10" in drafts["Election watch"]["x"]
    assert "Policy rate: 23%" in drafts["Election watch"]["linkedin"]
    assert drafts["Currencies"]["x"].startswith("67 days to Nigeria's general election: the naira is at 1,349 per US$")
    assert drafts["Stock movers"]["x"].startswith("67 days to Nigeria's general election: the NGX is +41.2%")
    assert drafts["Treasury bills"]["x"].splitlines()[2].startswith("Nigeria:")   # the election country leads
    for d in b["drafts"]:
        assert d["x"] is None or mb._x_len(d["x"]) <= mb.X_LIMIT


def test_no_election_angle_outside_the_window():
    ov, inst = _with_ngx()
    b = mb.build(ov, inst, EVENTS, date(2026, 8, 1))
    assert not any(s["title"].startswith("Election watch") for s in b["sections"])
    assert all(d["kind"] != "Election watch" and "election" not in (d["x"] or "") for d in b["drafts"])
