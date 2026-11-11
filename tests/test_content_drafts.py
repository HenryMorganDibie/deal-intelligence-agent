from datetime import date

import pytest
from fastapi.testclient import TestClient

from src import hosted_market as hm
from src.engines import content_drafts as cd

TODAY = date(2026, 11, 10)          # a Tuesday


def deal(i, **kw):
    base = {"id": f"d{i}", "announced": "2026-11-09", "country": "NG", "deal_type": "equity_funding",
            "target": f"Company {i}", "amount_usd": 1e6 * i, "round": "Series A", "investors": ["Partech", "TLcom"],
            "sources": [{"url": f"https://news.example/{i}", "publisher": "TechCabal", "date": "2026-11-09"}]}
    return {**base, **kw}


def test_sentences_use_only_stored_facts():
    assert cd.summary(deal(1, lead_investors=["Partech"])) == "Company 1 raised $1M Series A round, led by Partech"
    assert cd.summary(deal(2, deal_type="acquisition", buyer="MTN", target="Ayoba", stake_pct=None,
                           amount_usd=None)) == "MTN acquired Ayoba"
    assert cd.summary(deal(3, deal_type="exit", seller="Helios", target="Vivo Energy", buyer="Vitol", stake_pct=40,
                           amount_usd=2.3e9)) == "Helios sold its 40% stake in Vivo Energy to Vitol for $2.3B"
    assert cd.summary(deal(4, deal_type="acquisition", buyer=None)) is None      # missing parties: no post
    assert cd.money(12_500_000) == "$12.5M" and cd.money(None) is None
    assert cd.summary(deal(5, investors=["TPG"])) == "Company 5 raised $5M Series A round from TPG"
    assert cd.summary(deal(6, deal_type="debt_financing", investors=["Victory Park Capital", "Victory Park Capital Advisors"])) \
        == "Company 6 secured $6M in debt financing from Victory Park Capital"


def test_aggregator_links_are_left_out_but_the_publisher_is_named():
    d = deal(1, sources=[{"url": "https://news.google.com/rss/articles/CBMi", "publisher": "Business Insider Africa"}])
    post = cd.deal_of_the_day(d)["linkedin"]
    assert "news.google.com" not in post and "Source: Business Insider Africa" in post


def test_a_company_appears_once_in_the_roundup():
    out = cd.roundup([deal(9, target="Yoco"), deal(5, target="SA Fintech Yoco", deal_type="debt_financing"), deal(2)],
                     "the last 24 hours")
    assert out["deal_ids"] == ["d9", "d2"]


def test_daily_drafts_lead_with_the_largest_deal_and_fit_on_x():
    out = cd.build([deal(1), deal(9, target="Moniepoint"), deal(3), deal(5, announced="2026-10-01")], TODAY)
    kinds = [d["kind"] for d in out["drafts"]]
    assert kinds == ["Deal of the day", "More deals for X (1 of 2)", "More deals for X (2 of 2)", "Roundup"] \
        and out["deals_in_window"] == 3
    top = out["drafts"][0]
    assert top["deal_ids"] == ["d9"] and "Moniepoint raised $9M" in top["linkedin"]
    assert "https://news.example/9" in top["linkedin"]
    for d in out["drafts"]:
        assert d["x"] is None or cd.x_length(d["x"]) <= cd.X_LIMIT
        assert "—" not in (d.get("linkedin") or "") and "—" not in (d["x"] or "")


def test_monday_adds_the_week_in_review():
    week = [deal(i, announced=f"2026-11-0{i + 2}", investors=["Partech"]) for i in range(1, 6)]
    out = cd.build(week, date(2026, 11, 9))
    review = next(d for d in out["drafts"] if d["kind"] == "Week in review")
    assert "5 deals tracked, $15M disclosed" in review["linkedin"] and "Partech (5 deals)" in review["linkedin"]


def test_quiet_days_widen_the_window_then_send_nothing():
    assert cd.build([deal(1, announced="2026-11-07")], TODAY)["window"] == "the last three days"
    out = cd.build([], TODAY)
    assert out["drafts"] == [] and "no new deals" in cd.render_email(out)[0]


def test_email_escapes_and_labels_each_platform():
    subject, body, text = cd.render_email(cd.build([deal(1, target="A&B <Co>"), deal(2)], TODAY))
    assert "3 posts ready" in subject and "A&amp;B &lt;Co&gt;" in body and "LinkedIn" in text and "-- X (" in text


@pytest.fixture
def cron(monkeypatch):
    monkeypatch.setattr(hm, "_authorized_cron", lambda r: True)
    monkeypatch.setattr(hm, "deals", lambda: [deal(1), deal(2)])
    sent = []

    async def fake_send(client, to, subject, body, text, unsubscribe, key, **kw):
        sent.append((to, subject, key))
        return {"sent": True, "status": 200, "error": None}
    monkeypatch.setattr(hm.email_alerts, "send", fake_send)
    return sent


def client():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(hm.router)
    return TestClient(app)


def test_nothing_is_sent_without_a_recipient(cron, monkeypatch):
    monkeypatch.delenv("CONTENT_DRAFTS_TO", raising=False)
    r = client().get("/api/cron/content-drafts")
    assert r.status_code == 200 and r.json()["sent"] is False and cron == []


def test_sends_once_per_day_to_the_configured_owner(cron, monkeypatch):
    monkeypatch.setenv("CONTENT_DRAFTS_TO", "owner@example.com")
    r = client().get("/api/cron/content-drafts")
    assert r.json()["sent"] is True and cron[0][0] == "owner@example.com"
    client().get("/api/cron/content-drafts")
    assert cron[0][2] == cron[1][2]          # same idempotency key: the provider delivers it once


def test_requires_a_scheduled_caller(monkeypatch):
    monkeypatch.setattr(hm, "_authorized_cron", lambda r: False)
    assert client().get("/api/cron/content-drafts").status_code == 401


def test_a_figure_from_the_companys_history_is_not_the_deal():
    from src.engines import deals
    d = deals.extract_deal("After channelling $397 million to 40,000 businesses, TPG-backed Yoco secures $100 million "
                           "from US investor to take South African lending in-house", published="2026-11-09")
    assert d["amount_usd"] == 100e6 and d["investors"] == [] and d["existing_backers"] == ["TPG"]


def test_stored_records_drop_history_figures_and_existing_backers():
    from src.engines import deals
    fix = deals.reclassify({"deal_type": "equity_funding", "target": "Yoco", "amount": 397e6, "currency": "USD",
                            "amount_usd": 397e6, "announced": "2026-11-09", "investors": ["TPG"],
                            "headline": "After channelling $397 million to 40,000 businesses, TPG-backed Yoco secures "
                                        "$100 million from US investor to take South African lending in-house"})
    assert fix["amount_usd"] == 100e6 and fix["investors"] == [] and fix["existing_backers"] == ["TPG"]
    fund = {"deal_type": "fund_raise", "target": "Undisclosed private equity firm", "investors": ["Dangote"],
            "amount": 140e6, "currency": "USD",
            "headline": "Dangote-Backed Private Equity Firm Secures $140 Million In Initial Funding For $500 Million Fund"}
    assert deals.reclassify(fund) is None or "investors" not in deals.reclassify(fund)


def test_a_repeat_run_on_the_same_day_is_not_a_failure(cron, monkeypatch):
    monkeypatch.setenv("CONTENT_DRAFTS_TO", "owner@example.com")

    async def duplicate(*a, **kw):
        return {"sent": False, "status": 409, "error": "http_409"}
    monkeypatch.setattr(hm.email_alerts, "send", duplicate)
    body = client().get("/api/cron/content-drafts").json()
    assert body["sent"] is True and body["already_sent"] is True


def test_more_deals_for_x_and_a_fact_from_the_database():
    from datetime import date as _date
    from src.engines import content_drafts as cd
    base = {"deal_type": "equity_funding", "sources": [{"url": "https://a", "date": "2026-11-10"}]}
    history = [{**base, "id": f"h{i}", "target": f"Co{i}", "investors": ["Proparco"], "country": "KE",
                "announced": "2026-03-01", "amount_usd": 1e6} for i in range(8)]
    today = [{**base, "id": "a", "target": "Alpha", "investors": ["X"], "country": "NG", "announced": "2026-11-10", "amount_usd": 9e6},
             {**base, "id": "b", "target": "Beta", "investors": ["Y"], "country": "GH", "announced": "2026-11-10", "amount_usd": 5e6},
             {**base, "id": "c", "target": "Cashi", "investors": ["Proparco"], "country": "SD", "announced": "2026-11-10",
              "amount_usd": 652174}]
    res = cd.build(history + today, _date(2026, 11, 11))
    kinds = [d["kind"] for d in res["drafts"]]
    assert kinds[:3] == ["Deal of the day", "More deals for X (1 of 2)", "More deals for X (2 of 2)"]
    cashi = next(d for d in res["drafts"] if d.get("deal_ids") == ["c"])
    assert "Proparco's first deal in Sudan that we track, out of 9" in cashi["x"]
    assert all(cd.x_length(d["x"]) <= cd.X_LIMIT for d in res["drafts"] if d.get("x"))


def test_market_post_names_the_strongest_sector_and_skips_implausible_moves():
    from src.engines import content_drafts as cd
    ov = {"coverage": {"exchanges": 24}, "exchange_country": {"egx": "EG"},
          "sectors": [{"sector": "Telecom", "shares": 17, "mcap_usd": 69e9, "ytd_usd": 0.55},
                      {"sector": "Oil & Gas", "shares": 26, "mcap_usd": 18e9, "ytd_usd": 0.71},
                      {"sector": "Financials", "shares": 252, "mcap_usd": 129e9, "ytd_usd": 0.03},
                      {"sector": "Banque", "shares": 2, "mcap_usd": 4e9, "ytd_usd": 3.0}],
          "gainers": [{"name": "Glitch Co", "exchange": "egx", "chg_1d": 4.0}, {"name": "Delta", "exchange": "egx", "chg_1d": 0.2}]}
    post = cd.market_post(ov)
    assert "oil & gas stocks are up 71%" in post["linkedin"] and "24 exchanges" in post["linkedin"]
    assert "Glitch" not in post["linkedin"] and "Delta (Egypt), up 20%" in post["linkedin"]


def test_ipo_bids_are_demand_not_the_offer_size():
    from src.engines import deals as dm
    r = dm.extract_deal("Dangote Refinery Gets $4.1 Billion Share Bids in Top Africa IPO", published="2026-11-10")
    assert r is None or not r.get("amount_usd")
