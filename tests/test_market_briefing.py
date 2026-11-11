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
