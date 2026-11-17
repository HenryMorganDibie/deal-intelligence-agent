import gzip
import json

import httpx

from src import company_archive as ca


def _record(status: str = "200 OK", ctype: str = "text/html", body: str = "<html><title>About</title><p>Hi</p></html>"):
    warc = b"WARC/1.0\r\nWARC-Type: response\r\nWARC-Date: 2026-10-12T08:00:00Z\r\n"
    http = f"HTTP/1.1 {status}\r\nContent-Type: {ctype}\r\n".encode()
    return gzip.compress(warc + b"\r\n" + http + b"\r\n" + body.encode())


def test_robots_rule_for_the_archive():
    assert ca.ccbot_allowed("User-agent: *\nDisallow: /admin\n", "https://acme.com/about") is True
    assert ca.ccbot_allowed("User-agent: CCBot\nDisallow: /\n", "https://acme.com/about") is False
    assert ca.ccbot_allowed(None, "https://acme.com/about") is True      # unreadable: the archive checked it


def test_warc_record_parsing():
    assert ca.parse_record(_record()) == ("2026-10-12", "<html><title>About</title><p>Hi</p></html>")
    assert ca.parse_record(_record(status="301 Moved")) is None
    assert ca.parse_record(_record(ctype="application/pdf")) is None
    assert ca.parse_record(b"not gzip") is None


def _client(calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/collinfo.json":
            return httpx.Response(200, json=[{"id": "CC-MAIN-2026-43"}, {"id": "CC-MAIN-2026-39"}])
        if request.url.host == "index.commoncrawl.org":
            if request.url.params.get("url") == "acme.com/about":
                row = {"url": "https://acme.com/about", "status": "200", "mime": "text/html",
                       "filename": "crawl-data/x.warc.gz", "offset": "10", "length": "99"}
                return httpx.Response(200, text=json.dumps(row) + "\n")
            return httpx.Response(404, text='{"message": "No Captures found"}')
        if request.url.host == "data.commoncrawl.org":
            assert request.headers["range"] == "bytes=10-108"
            return httpx.Response(206, content=_record(body="<html><title>About Acme</title><p>Founded in 2015 by Ada.</p></html>"))
        return httpx.Response(500)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_archived_pages_read_the_company_s_own_page(monkeypatch):
    monkeypatch.setattr(ca, "_crawls", None)
    calls: list = []
    pages = ca.archived_pages("https://www.acme.com/", "User-agent: *\nAllow: /\n", client=_client(calls))
    assert [(p["url"], p["title"], p["archived_at"]) for p in pages] == [("https://acme.com/about", "About Acme", "2026-10-12")]
    assert "Founded in 2015 by Ada." in pages[0]["text"]


def test_no_archive_request_when_robots_forbids_ccbot(monkeypatch):
    monkeypatch.setattr(ca, "_crawls", None)
    calls: list = []
    assert ca.archived_pages("https://acme.com", "User-agent: CCBot\nDisallow: /\n", client=_client(calls)) == []
    assert calls == []
