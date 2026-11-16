"""On-the-spot company reads: page parsing, report search, robots and the agent the reader identifies as."""
import httpx

from src import company_live as cl


def test_page_text_and_links_survive_a_page_wrapped_in_header():
    html = ("<html><head><title>Acme | About</title><script>var x=1</script></head><body><header>"
            "<h1>About Acme</h1><p>Acme Plc was founded in 1990.</p><a href='/board'>Board</a>"
            "<a href='mailto:x@acme.com'>mail</a></header></body></html>")
    page = cl._Page("https://acme.com/about")
    page.feed(html)
    assert "Acme Plc was founded in 1990." in page.text() and "var x" not in page.text()
    assert page.title.strip() == "Acme | About" and page.links == ["https://acme.com/board"]


def test_report_search_keeps_own_domain_or_exchange_full_reports(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test")
    rows = [{"url": "https://www.safaricom.co.ke/images/Downloads/2025-Annual-Report.pdf", "title": "Annual report"},
            {"url": "https://www.safaricom.co.ke/images/Downloads/2026-Annual-Report.pdf", "title": "Annual report"},
            {"url": "https://www.safaricom.co.ke/images/Downloads/2026-Half-Year-Results.pdf", "title": "Results"},
            {"url": "https://randomblog.com/safaricom-annual-report-2026.pdf", "title": "Annual report"},
            {"url": "https://doclib.ngxgroup.com/x/ACME_2025_annual_report.pdf", "title": "Annual report"}]
    monkeypatch.setattr(cl.httpx, "post", lambda *a, **k: httpx.Response(200, json={"results": rows}))
    assert cl.search_report("Safaricom PLC") == "https://www.safaricom.co.ke/images/Downloads/2026-Annual-Report.pdf"
    monkeypatch.setattr(cl.httpx, "post", lambda *a, **k: httpx.Response(200, json={"results": rows[3:]}))
    assert cl.search_report("Acme Plc") == "https://doclib.ngxgroup.com/x/ACME_2025_annual_report.pdf"
    monkeypatch.delenv("TAVILY_API_KEY")
    assert cl.search_report("Acme Plc") is None


def test_robots_are_honoured_under_the_readers_own_name():
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: DealIntelligence\nDisallow: /private\n")
        return httpx.Response(200, text="<html><body>ok</body></html>", headers={"content-type": "text/html"})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    robots = cl._Robots(client)
    assert robots.allowed("https://acme.com/about") and not robots.allowed("https://acme.com/private/x")
    assert "DealIntelligence" in cl.USER_AGENT and "deal-intelligence.app" in cl.USER_AGENT


def test_crawl_reads_the_home_page_and_its_company_pages_only():
    pages = {"/": "<a href='/about-us'>About</a><a href='/careers'>Jobs</a><a href='https://other.com/about'>x</a>"
                  "<a href='/board-of-directors'>Board</a><a href='/annual-report-2025.pdf'>AR</a>",
             "/about-us": "<p>About us</p>", "/board-of-directors": "<p>Our board</p>"}

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        body = pages.get(request.url.path)
        return httpx.Response(200 if body else 404, text=f"<html><body>{body or ''}</body></html>",
                              headers={"content-type": "text/html"})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    got = cl.crawl("https://acme.com/", client)
    assert got[0]["final_url"] == "https://acme.com/"
    assert {p["final_url"] for p in got[1:]} == {"https://acme.com/board-of-directors", "https://acme.com/about-us"}
    assert "https://acme.com/annual-report-2025.pdf" in got[0]["links"]


def test_public_sources_skip_old_documents_and_thin_results(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test")
    year = int(__import__("time").strftime("%Y"))
    rows = [{"url": "https://en.wikipedia.org/wiki/Acme", "title": "Acme", "content": "Acme was founded in 1990. " * 5},
            {"url": f"https://acme.com/uploads/{year - 4}/report.pdf", "title": "Old", "content": "Old board list. " * 10},
            {"url": "https://acme.com/about", "title": "About", "content": "short"}]
    monkeypatch.setattr(cl.httpx, "post", lambda *a, **k: httpx.Response(200, json={"results": rows}))
    got = cl.public_pages("Acme Plc")
    assert [p["url"] for p in got] == ["https://en.wikipedia.org/wiki/Acme"]
    assert got[0]["status_code"] == 200 and "founded in 1990" in got[0]["text"]
    monkeypatch.delenv("TAVILY_API_KEY")
    assert cl.public_pages("Acme Plc") == []
