"""Open-web evidence for research and the Gemini provider."""
import httpx

from src.agents import signal_agent as sa
from src.engines import research


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_web_search_returns_pages_with_their_own_urls(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test")
    seen = {}

    def handler(request):
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"results": [
            {"url": "https://moniepoint.com/news/series-c", "title": "Moniepoint raises", "content": "x" * 60,
             "published_date": "2026-10-02T00:00:00Z"},
            {"url": "http://insecure.example/a", "title": "t", "content": "y" * 60},
            {"url": "https://short.example/a", "title": "t", "content": "too short"}]})

    out = research.web_search("Moniepoint funding", {"countries": ["NG"], "since": "2026-01-01"}, _client(handler))
    assert [o["url"] for o in out] == ["https://moniepoint.com/news/series-c"]
    assert out[0]["source"] == "moniepoint.com" and out[0]["date"] == "2026-10-02"
    assert "Nigeria" in seen["body"] and "2026-01-01" in seen["body"]


def test_web_search_is_skipped_without_a_key_and_survives_failures(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert research.web_search("q", {}) == []
    monkeypatch.setenv("TAVILY_API_KEY", "test")
    assert research.web_search("q", {}, _client(lambda r: httpx.Response(432, json={}))) == []


def test_gemini_falls_through_busy_models(monkeypatch):
    monkeypatch.setattr(sa, "GEMINI_MODELS", ["busy", "good"])
    calls = []

    def handler(request):
        model = __import__("json").loads(request.read())["model"]
        calls.append(model)
        if model == "busy":
            return httpx.Response(503, json={"error": {"message": "high demand"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "answer [1]"}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test")
    assert sa._call_llm_uncached(client, "gemini", "s", "u", 100) == "answer [1]"
    assert calls == ["busy", "good"] and sa._last_model["gemini"] == "good"
