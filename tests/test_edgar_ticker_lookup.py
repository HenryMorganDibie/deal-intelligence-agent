import asyncio

import httpx

from src.tools import edgar_tool as et


def _tool(handler):
    tool = et.EdgarTool()
    tool._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return tool


def test_tickers_resolve_from_secs_own_list(monkeypatch):
    """EDGAR's browse page refuses count=5 (400), so tickers resolve from company_tickers.json."""
    monkeypatch.setattr(et, "_SEC_TICKERS", None)
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.path == "/files/company_tickers.json":
            return httpx.Response(200, json={"0": {"cik_str": 1507605, "ticker": "MARA", "title": "MARA Holdings, Inc."}})
        return httpx.Response(400, text="Invalid count")
    tool = _tool(handler)
    got = asyncio.run(tool.resolve_company("Marathon", "mara"))
    assert got == {"cik": "0001507605", "name": "MARA Holdings, Inc.", "ticker": "MARA"}
    asyncio.run(tool.resolve_company("Marathon", "MARA"))
    assert sum("company_tickers" in u for u in seen) == 1              # the list is cached


def test_unknown_ticker_falls_back_to_the_browse_page_with_a_count_it_accepts(monkeypatch):
    monkeypatch.setattr(et, "_SEC_TICKERS", None)
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.path == "/files/company_tickers.json":
            return httpx.Response(200, json={})
        return httpx.Response(200, text="<feed><company-name>Some Co</company-name> CIK=0000000042 </feed>")
    got = asyncio.run(_tool(handler).resolve_company("Some Co", "SOME"))
    assert got["cik"] == "0000000042"
    assert all("count=5&" not in u for u in seen) and any("count=10" in u for u in seen)
