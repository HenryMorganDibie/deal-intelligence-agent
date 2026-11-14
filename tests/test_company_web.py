"""Company websites read with web-harvester: queue, crawl config, reading the pages, storing the facts."""
import json

from src import company_web as cw


def test_websites_are_normalised_to_a_home_page_and_social_pages_refused():
    assert cw.normalise_site("www.mtnonline.com") == "https://www.mtnonline.com/"
    assert cw.normalise_site("http://Dangote.com/about") == "https://dangote.com/"
    assert cw.normalise_site("https://www.linkedin.com/company/x") is None
    assert cw.normalise_site("not a site") is None and cw.normalise_site(None) is None


def test_crawl_target_follows_only_pages_that_say_what_they_hold():
    t = cw.target({"name_key": "mtn nigeria", "name": "MTN Nigeria", "website": "https://www.mtn.ng/"})
    assert t["start_urls"] == ["https://www.mtn.ng/"] and t["max_depth"] == 1 and t["max_pages"] == 12
    import re
    inc = [re.compile(p) for p in t["include"]]
    exc = [re.compile(p) for p in t["exclude"]]
    ok = lambda u: any(p.search(u) for p in inc) and not any(p.search(u) for p in exc)   # noqa: E731
    assert ok("https://www.mtn.ng/about-us/") and ok("https://www.mtn.ng/board-of-directors")
    assert ok("https://www.mtn.ng/investor/board") and ok("https://www.mtn.ng/contact")
    assert not ok("https://www.mtn.ng/careers/jobs") and not ok("https://www.mtn.ng/shop/data-plans")


PAGES = [
    {"target": "acme", "url": "https://acme.ng/", "status_code": 200, "depth": 0, "title": "Acme",
     "text": "Welcome to Acme. Founded in 1998.",
     "json_ld": [json.dumps({"@type": "Organization", "address": {"streetAddress": "12 Broad Street", "addressLocality": "Lagos"}})]},
    {"target": "acme", "url": "https://acme.ng/leadership", "status_code": 200, "depth": 1, "title": "Leadership",
     "text": "Our board: Ada Obi, Chairman. Management: John Bello, Managing Director. Call +234 1 234 5678 or info@acme.ng"},
    {"target": "acme", "url": "https://acme.ng/missing", "status_code": 404, "depth": 1, "text": ""},
]


def test_site_facts_are_kept_only_when_on_the_cited_page():
    def model(system, user):
        assert "[p 1] https://acme.ng/leadership" in user                # leadership pages are read first
        return json.dumps({
            "board": [{"name": "Ada Obi", "role": "Chairman", "page": 1}, {"name": "Made Up", "role": "Chairman", "page": 1}],
            "management": [{"name": "John Bello", "role": "Managing Director", "page": 1}],
            "phone": "+234 1 234 5678", "phone_page": 1, "email": "info@acme.ng", "email_page": 1,
            "founded": "1998", "founded_page": 2, "registered_office": "12 Broad Street, Lagos", "office_page": 2,
            "subsidiaries": [{"name": "Ghost Ltd", "page": 2}]})
    facts = cw.read_site({"name": "Acme", "website": "https://acme.ng/"}, PAGES, call=model)
    assert [b["name"] for b in facts["board"]] == ["Ada Obi"]
    assert facts["management"] == [{"name": "John Bello", "page": 1, "role": "Managing Director"}]
    assert facts["phone"] == "+234 1 234 5678" and facts["email"] == "info@acme.ng" and facts["founded"] == "1998"
    assert facts["registered_office"] == "12 Broad Street, Lagos"           # from the page's schema.org address
    assert "subsidiaries" not in facts
    assert [p["url"] for p in facts["pages"]] == ["https://acme.ng/leadership", "https://acme.ng/"]
    assert cw.read_site({"name": "Acme", "website": "x"}, [PAGES[2]], call=model) is None


def test_apply_stores_facts_and_marks_sites_without_pages_failed(monkeypatch):
    from src import hosted_market as hm
    saved = []

    class R:
        status_code = 200

        def json(self):
            return True
    monkeypatch.setattr(hm, "_rpc_sync", lambda fn, args, timeout=30: saved.append((fn, args)) or R())
    model = lambda s, u: json.dumps({"board": [{"name": "Ada Obi", "role": "Chairman", "page": 1}]})   # noqa: E731
    out = cw.apply_crawl([{"name_key": "acme", "name": "Acme", "website": "https://acme.ng/"},
                          {"name_key": "beta", "name": "Beta", "website": "https://beta.ng/"}], PAGES, call=model)
    assert out == {"sites": 2, "with_facts": 1, "pages": 3}
    by = {a["p_name_key"]: a for _, a in saved}
    assert by["acme"]["p_status"] == "done" and by["acme"]["p_facts"]["board"][0]["name"] == "Ada Obi"
    assert by["beta"]["p_status"] == "failed" and "robots" in by["beta"]["p_error"]


def test_profile_lookup_never_fails_when_the_queue_is_unavailable(monkeypatch):
    from src import hosted_market as hm
    monkeypatch.setattr(hm, "_configured", lambda: True)

    def broken(*a, **k):
        raise RuntimeError("relation company_web does not exist")
    monkeypatch.setattr(hm, "_rpc_sync", broken)
    assert cw.request("Acme Plc", "acme.ng") is None


def test_text_every_page_shares_is_dropped_so_the_page_content_is_read():
    menu = "Menu About Us Our History Executive Team Board Of Directors Products Contact Investor Relations Careers Media"
    pages = [f"{menu} Board of Directors Emmanuel Ikazoboh Chairman {menu}",
             f"{menu} Executive Team Arvind Pathak Group Managing Director {menu}",
             f"{menu} Contact Us Call +234 1 460 6430 {menu}"]
    out = cw.strip_shared(pages)
    assert out[0] == "Board of Directors Emmanuel Ikazoboh Chairman"
    assert out[2] == "Contact Us Call +234 1 460 6430"
    assert cw.strip_shared(pages[:2]) == pages[:2]                  # too few pages to tell the menu apart
