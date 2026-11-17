"""Opportunity sourcing: which real headlines are solicitations, how reports combine, and stored records."""
from src.engines import opportunities as op


def item(title, date="2026-11-09", hint=None, snippet="", publisher="Example"):
    return {"title": title, "date": date, "country_hint": hint, "snippet": snippet, "publisher": publisher,
            "url": "https://news.example/" + str(abs(hash(title)))}


ACCEPT = [
    ("NNPC Seeks Investors for $26B Gas Pipeline to Morocco and Europe", "MA", "Seeking investors"),
    ("Congo seeks investors for $12bn to fix power shortages", "CD", "Seeking investors"),
    ("Vodacom Seeks Partners to Build AI Data Centres in South Africa and Kenya", "ZA", "Seeking partners"),
    ("Algeria opens seven oil and gas blocks to international investors in 2026 Bid Round", "DZ", "Open for bids"),
    ("Rwanda seeks investors for 200MW solar project on Lake Sake | The New Times", "RW", "Seeking investors"),
]
REJECT = [
    "President Mahama woos investors to Ghana at Invest in Ghana Summit 2026",      # a place and an event
    "Ghana woos investors to drive production, jobs",                               # nothing specific
    "Media Authority seeks funding for nationwide campaign against election hate speech",
    "Ga Mantse backs GMTF, urges more investment in medical research",              # general call, and "backs"
    "Pecoy Copper secures C$49.8m strategic financing from Hudbay",                 # a completed deal
    "Nokian Tyres seeks partners for exoskeleton project",                          # not in Africa
    "Angola seeks 10% stake in De Beers under Anglo's proposed exit",               # a buyer, not a solicitation
]


def test_real_solicitations_are_extracted():
    for title, country, status in ACCEPT:
        r = op.extract(item(title))
        assert r, title
        assert r["country"] == country and r["opportunity_status"] == status, (title, r["country"], r["opportunity_status"])
        assert r["record_type"] == "investment_opportunity" and r["amount_usd"] is None
    assert op.extract(item(ACCEPT[0][0]))["amount_sought_usd"] == 26e9
    # Of the countries a story names, the search edition's comes first
    assert op.extract(item("Vodacom Seeks Partners to Build AI Data Centres in South Africa and Kenya", hint="KE"))["countries"] == ["KE", "ZA"]
    assert "|" not in op.extract(item(ACCEPT[4][0]))["headline"]


def test_general_calls_events_deals_and_foreign_stories_are_not():
    for title in REJECT:
        assert op.extract(item(title)) is None, title


def test_country_edition_places_a_story_only_when_it_names_no_country_and_is_not_pan_african():
    assert op.extract(item("Edo seeks private investment to boost electricity supply", hint="NG"))["country"] == "NG"
    assert op.extract(item("Vodacom seeks partners to build AI data centres across Africa", hint="EG")) is None


def test_reports_combine_and_attach_to_stored_records():
    a = op.extract(item("NNPC Seeks Investors for $26B Gas Pipeline to Morocco and Europe", publisher="PTJ"))
    b = op.extract(item("Nigeria seeks investors for Morocco Gas Pipeline", date="2026-11-08", publisher="Pumps Africa"))
    out = op.merge_into([a, b], [])
    assert len(out) == 1 and len(out[0]["sources"]) == 2
    stored = {**b, "id": "stored1", "reviewed_on": "2026-11-17"}
    again = op.merge_into([a], [stored])
    assert [r["id"] for r in again] == ["stored1"] and again[0]["reviewed_on"] == "2026-11-17"
    assert len(again[0]["sources"]) == 2


def test_list_of_parties_kept_whole():
    r = op.extract(item("Nigeria, UK seek private investment in three hydropower projects"))
    assert r["soliciting_party"] == "Nigeria, UK"
