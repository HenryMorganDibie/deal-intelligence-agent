from datetime import date

from src.engines import content_drafts as cd
from src.engines import deal_sanity as ds


def deal(i, **kw):
    base = {"id": f"d{i}", "announced": "2026-11-09", "country": "NG", "deal_type": "equity_funding",
            "target": f"Company {i}", "amount_usd": 2e6, "round": "seed", "investors": ["Partech"],
            "headline": f"Company {i} raises $2M seed", "independent_stories": 2,
            "sources": [{"url": "https://a.example", "publisher": "TechCabal"}, {"url": "https://b.example", "publisher": "Techpoint"}]}
    return {**base, **kw}


def test_a_clean_deal_has_no_flags():
    assert ds.flags(deal(1)) == []


def test_each_known_mistake_is_flagged():
    assert ds.flags(deal(1, target="Your Votes"))                                     # a sentence as a party
    assert ds.flags(deal(2, investors=["Lagos"]))                                     # a place as investor
    assert ds.flags(deal(3, investors=["Company 3"]))                                 # its own investor
    assert ds.flags(deal(4, amount_usd=80e6))                                         # too large for seed
    assert ds.flags(deal(5, round=None, amount_usd=397e6, independent_stories=1))    # big and single-source
    assert ds.flags(deal(6, headline="After channelling $397 million, Company 6 secures $100 million"))
    yoco = [deal(7, target="Yoco"), deal(8, target="SA Fintech Yoco", announced="2026-11-10")]
    assert "possible duplicate" in ds.flags(yoco[0], yoco)[0]


def test_flagged_deals_are_held_out_of_drafts_and_listed():
    out = cd.build([deal(1, amount_usd=3e6), deal(2), deal(9, amount_usd=900e6, round=None, independent_stories=1)],
                   date(2026, 11, 10))
    assert all("d9" not in d["deal_ids"] for d in out["drafts"])
    assert [h["id"] for h in out["held_back"]] == ["d9"]
    subject, body, text = cd.render_email(out)
    assert "Held back for review (1)" in body and "single source" in text
    assert "https://deal-intelligence.app/deals/d9" in text
