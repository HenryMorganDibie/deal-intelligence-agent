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
    assert t["start_urls"] == ["https://www.mtn.ng/"] and t["max_depth"] == 1 and t["max_pages"] == 16
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
    assert {k: out[k] for k in ("sites", "with_facts", "pages")} == {"sites": 2, "with_facts": 1, "pages": 3}
    assert [d["company"] for d in out["detail"]] == ["acme", "beta"]
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


def test_the_newest_full_annual_report_is_found_among_the_site_links():
    pages = [{"links": ["https://x.com/files/annual-report-2023.pdf", "https://x.com/files/Integrated_Annual_Report_2025.pdf",
                        "https://x.com/files/annual-report-2025-summary.pdf", "https://x.com/files/agm-notice-2025.pdf",
                        "https://x.com/about", "https://x.com/files/2025-annual-financial-statements.pdf"]}]
    assert cw.find_report(pages) in ("https://x.com/files/Integrated_Annual_Report_2025.pdf",
                                     "https://x.com/files/2025-annual-financial-statements.pdf")
    assert cw.find_report([{"links": ["https://x.com/brochure.pdf"]}]) is None


def test_robots_txt_is_not_consulted_for_reports_or_the_crawl(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "get", lambda url, **k: (_ for _ in ()).throw(AssertionError("robots.txt fetched")))
    assert cw._robots_allow("https://x.com/files/annual-report-2025.pdf") is True
    assert cw.target({"name_key": "acme", "website": "https://acme.com"})["respect_robots"] is False


def test_a_company_with_only_a_scanned_filing_is_queued_and_read(monkeypatch):
    from src import hosted_market as hm
    calls = []

    class R:
        status_code = 200

        def json(self):
            return {"status": "queued"}
    monkeypatch.setattr(hm, "_configured", lambda: True)
    monkeypatch.setattr(hm, "_rpc_sync", lambda fn, args, timeout=30: calls.append((fn, args)) or R())
    monkeypatch.setattr(cw, "wikidata_website", lambda name, country=None: None)
    cw.request("Acme Plc", None, "NG", "https://doclib.ngxgroup.com/acme-2025.pdf")
    assert calls[0] == ("company_web_request", {"p_name_key": "acme", "p_name": "Acme Plc", "p_website": None,
                                                "p_filing_url": "https://doclib.ngxgroup.com/acme-2025.pdf"})
    cfg_companies = [{"name_key": "acme", "name": "Acme Plc", "website": None, "filing_url": "https://x/acme.pdf"}]
    monkeypatch.setattr(cw, "read_filing", lambda c, call=None: {"rc_number": "123456", "ocr": True})
    saved = []
    monkeypatch.setattr(hm, "_rpc_sync", lambda fn, args, timeout=30: saved.append(args) or R())
    assert cw.apply_crawl(cfg_companies, [])["with_facts"] == 1
    assert saved[-1]["p_status"] == "done" and saved[-1]["p_facts"]["filing"]["ocr"] is True


def test_wikidata_supplies_a_website_only_for_a_matching_company(monkeypatch):
    responses = {
        "wbsearchentities": {"search": [{"id": "Q1"}, {"id": "Q2"}]},
        "wbgetentities": {"entities": {
            "Q1": {"labels": {"en": {"value": "Acme Cement"}}, "claims": {
                "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q4830453"}}}}],
                "P856": [{"mainsnak": {"datavalue": {"value": "http://www.acme.ng"}}}]}},
            "Q2": {"labels": {"en": {"value": "Acme Cement (book)"}}, "claims": {}}}},
    }
    monkeypatch.setattr(cw, "_wikidata", lambda params: responses[params["action"]])
    assert cw.wikidata_website("Acme Cement") == "https://www.acme.ng/"
    assert cw.wikidata_website("Other Name") is None
    responses["wbgetentities"]["entities"]["Q1"]["claims"]["P31"] = [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]
    assert cw.wikidata_website("Acme Cement") is None                     # not a company


def test_web_search_accepts_only_the_company_own_domain(monkeypatch):
    import httpx

    class R:
        status_code = 200

        def __init__(self, results):
            self._r = results

        def json(self):
            return {"results": self._r}
    results = [{"url": "https://www.linkedin.com/company/moniepoint"}, {"url": "https://techcabal.com/moniepoint-raises"},
               {"url": "https://moniepoint.com/ng/about"}, {"url": "https://other.com/"}]
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    sent = {}
    monkeypatch.setattr(httpx, "post", lambda url, headers=None, json=None, timeout=None: sent.update(json=json, headers=headers) or R(results))
    assert cw.search_website("Moniepoint Inc") == "https://moniepoint.com/"
    assert "official website" in sent["json"]["query"] and sent["headers"]["Authorization"] == "Bearer test-key"
    monkeypatch.setattr(httpx, "post", lambda *a, **k: R([{"url": "https://nairametrics.com/acme"}, {"url": "https://unrelated.io/"}]))
    assert cw.search_website("Acme Holdings") is None
    assert cw._name_in_domain("Guaranty Trust Holding Company", "www.gtco.com")            # initials
    monkeypatch.delenv("TAVILY_API_KEY")
    assert cw.search_website("Moniepoint") is None                                         # no key: no search


def test_profile_defers_governance_to_its_own_request(monkeypatch):
    """The board read takes several model passes: build leaves it out and says which filing to read."""
    from src.engines import company_profile as cp
    called = []
    monkeypatch.setattr(cp, "_ngx_section", lambda t, f=None: {
        "identity": {"name": "Acme Plc"},
        "financials": {"source_url": "https://ngxgroup.com/a.pdf", "source": "NGX: FY", "filed": "2026-04-01"}})
    monkeypatch.setattr(cp, "_governance", lambda *a: called.append(a) or {"board": []})
    p = cp.build("Acme", "ACME.LG", "NG", with_governance=False)
    assert not called and "governance" not in p
    assert p["governance_source"]["url"] == "https://ngxgroup.com/a.pdf"
    p = cp.build("Acme", "ACME.LG", "NG")
    assert called and p["governance"] == {"board": []}


def test_store_filing_merges_with_stored_facts(monkeypatch):
    from src import company_web, hosted_market as hm
    calls = []

    class R:
        def __init__(self, body):
            self.status_code, self._b = 200, body

        def json(self):
            return self._b

    def rpc(fn, args, timeout):
        calls.append((fn, args))
        return R({"status": "done", "facts": {"website": "https://acme.com"}} if fn == "company_web_get" else True)

    monkeypatch.setattr(hm, "_configured", lambda: True)
    monkeypatch.setattr(hm, "_rpc_sync", rpc)
    assert company_web.store_filing("Acme Plc", {"board": [{"name": "A"}]})
    fn, args = calls[-1]
    assert fn == "company_web_save" and args["p_status"] == "done"
    assert args["p_facts"] == {"website": "https://acme.com", "filing": {"board": [{"name": "A"}]}}


def test_crawl_config_processes_independent_sites_concurrently_and_keeps_host_rate_limit(monkeypatch):
    from src import hosted_market as hm

    class R:
        status_code = 200

        def json(self):
            return [
                {"name_key": "alpha", "name": "Alpha Plc", "website": "https://alpha.example/"},
                {"name_key": "beta", "name": "Beta Plc", "website": "https://beta.example/"},
            ]

    monkeypatch.setattr(hm, "_rpc_sync", lambda *a, **k: R())
    monkeypatch.setattr(cw, "resolve", lambda site: site.replace("www.", ""))
    cfg, companies = cw.crawl_config("pages.jsonl")
    assert len(companies) == 2
    assert cfg["concurrency"] == 8
    assert cfg["rate_per_host_rps"] == 0.5
    assert {t["name"] for t in cfg["targets"]} == {"alpha", "beta"}


def test_apply_crawl_extracts_companies_in_parallel_and_persists_each(monkeypatch):
    import threading
    from src import hosted_market as hm

    worker_threads = []
    saved = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    class R:
        status_code = 200

        def json(self):
            return True

    monkeypatch.setattr(cw, "_stored_facts", lambda key: {})
    def read_site(company, pages, call=None):
        barrier.wait(timeout=5)
        worker_threads.append(threading.current_thread().name)
        return {"phone": company["name"]}

    monkeypatch.setattr(cw, "read_site", read_site)
    monkeypatch.setattr(cw, "read_report", lambda *a, **k: None)
    monkeypatch.setattr(cw, "read_filing", lambda *a, **k: None)

    def rpc(fn, args, timeout=30):
        with lock:
            saved.append((fn, args))
        return R()

    monkeypatch.setattr(hm, "_rpc_sync", rpc)
    companies = [
        {"name_key": "alpha", "name": "Alpha Plc", "website": "https://alpha.example/"},
        {"name_key": "beta", "name": "Beta Plc", "website": "https://beta.example/"},
    ]
    pages = [{"target": "alpha", "status_code": 200, "text": "Alpha"},
             {"target": "beta", "status_code": 200, "text": "Beta"}]
    out = cw.apply_crawl(companies, pages)
    assert out["with_facts"] == 2
    assert len(out["detail"]) == 2
    assert all(name.startswith("ThreadPoolExecutor") for name in worker_threads)
    final = {args["p_name_key"]: args for fn, args in saved if fn == "company_web_save" and args["p_status"] == "done"}
    assert set(final) == {"alpha", "beta"}


def test_official_website_discovery_uses_the_shared_hourly_search_budget(monkeypatch):
    from src import hosted_market as hm

    calls = []

    class R:
        status_code = 200

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    def rpc(fn, args, timeout=30):
        calls.append((fn, args))
        if fn == "company_web_take":
            return R([{"name_key": "acme", "name": "Acme Plc", "website": None, "search_allowed": True}])
        return R("queued")

    monkeypatch.setattr(hm, "_rpc_sync", rpc)
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(cw, "search_website", lambda name: "https://acme.example/")
    monkeypatch.setattr(cw, "resolve", lambda site: site)
    cfg, companies = cw.crawl_config("pages.jsonl")
    assert cfg["targets"][0]["start_urls"] == ["https://acme.example/"]
    assert companies[0]["website_source"] == "Tavily web search"
    assert calls[0] == ("company_web_take", {"p_limit": cw.SITES_PER_RUN, "p_search_enabled": True})
    assert any(fn == "company_web_request" for fn, _ in calls)


def test_seed_order_listed_by_value_then_licensed_with_site_then_busiest_private():
    rows = [
        {"kind": "private", "name": "Busy Startup", "country": "NG", "deal_count": 5},
        {"kind": "listed", "name": "Small Plc", "country": "NG", "mcap_usd": 1e7},
        {"kind": "listed", "name": "Big Plc", "country": "NG", "mcap_usd": 9e9},
        {"kind": "listed", "name": "Big Plc Secondary", "country": "KE", "mcap_usd": 9e9, "secondary_of": "Big Plc"},
        {"kind": "private", "name": "Quiet Startup", "country": "NG", "deal_count": 1},
        {"kind": "listed", "name": "Global Mining Group", "country": "ZA", "mcap_usd": 9e11, "foreign_primary": True},
    ]
    names = [n for n, _, _ in cw.seed_candidates(rows)]
    assert names == ["Big Plc", "Small Plc", "Global Mining Group", "Busy Startup"]  # foreign primaries after African listings


def test_seed_skips_companies_already_read_or_queued(monkeypatch):
    from unittest.mock import MagicMock
    from src import hosted_market as hm
    monkeypatch.setattr(hm, "_configured", lambda: True)
    known = {cw.name_key("Big Plc")}
    monkeypatch.setattr(hm, "_rpc_sync", lambda fn, args, t=10: MagicMock(
        status_code=200, json=lambda: ({"status": "done"} if args["p_name_key"] in known else None)))
    asked = []
    monkeypatch.setattr(cw, "request", lambda name, site, country=None: asked.append(name) or {"status": "queued"})
    rows = [{"kind": "listed", "name": n, "country": "NG", "mcap_usd": v} for n, v in
            (("Big Plc", 9e9), ("Mid Plc", 5e8), ("Small Plc", 1e7))]
    assert cw.seed(rows, limit=1) == {"queued": ["Mid Plc"], "checked": 2}
    assert asked == ["Mid Plc"]


# ── Re-reading sites that change ──────────────────────────────────────────────

def test_fingerprint_follows_governance_and_report_links_not_news():
    from src import company_web as cw
    base = "https://www.acme.co/"
    page = ('<a href="/about-us">About</a><a href="/board-of-directors/">Board</a>'
            '<a href="https://acme.co/investors/annual-report-2025.pdf">AR</a>'
            '<a href="/news/today">News</a><a href="https://other.com/board">x</a>')
    fp = cw.site_fingerprint(page, base)
    assert fp and fp == cw.site_fingerprint(page + '<a href="/news/tomorrow">More news</a>', base)   # news ignored
    assert fp == cw.site_fingerprint(page.replace('/board-of-directors/', '/board-of-directors'), base)
    new_report = page + '<a href="/investors/annual-report-2026.pdf">AR 2026</a>'
    assert cw.site_fingerprint(new_report, base) != fp                                               # new report
    assert cw.site_fingerprint('<a href="/news">News</a>', base) is None


def test_refresh_queues_changed_sites_and_reports_unreadable_ones(monkeypatch):
    from src import company_web as cw
    from src import hosted_market as hm

    class R:
        def __init__(self, payload):
            self.status_code, self._p, self.text = 200, payload, str(payload)

        def json(self):
            return self._p
    calls = []

    def rpc(fn, args, timeout=30):
        calls.append((fn, args))
        if fn == "company_web_due_checks":
            return R([{"name_key": "acme", "name": "Acme", "website": "https://acme.co"},
                      {"name_key": "beta", "name": "Beta", "website": "https://beta.co"}])
        return R("queued" if args["p_name_key"] == "acme" else "unchanged")
    monkeypatch.setattr(hm, "_configured", lambda: True)
    monkeypatch.setattr(hm, "_rpc_sync", rpc)
    monkeypatch.setattr(cw, "_home_fingerprint", lambda site: "fp1" if "acme" in site else None)
    out = cw.refresh(10)
    assert out == {"checked": 2, "queued_for_reread": ["Acme"], "unreadable": ["Beta"]}
    assert ("company_web_checked", {"p_name_key": "beta", "p_fingerprint": None}) in calls
