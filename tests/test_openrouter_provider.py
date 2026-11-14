"""OpenRouter's free models as a language model provider, tried in order, falling through on limits."""
from src.agents import signal_agent as sa


class _Resp:
    def __init__(self, status, payload):
        self.status_code, self._p = status, payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._p


class _Client:
    def __init__(self, answers):
        self.answers, self.models = answers, []

    def post(self, path, json=None):
        assert path == "/chat/completions"
        self.models.append(json["model"])
        return self.answers.pop(0)


def test_openrouter_tries_the_free_models_in_order(monkeypatch):
    monkeypatch.setattr(sa, "OPENROUTER_MODELS", ["a/one:free", "b/two:free"])
    client = _Client([_Resp(429, {}), _Resp(200, {"choices": [{"message": {"content": "<think>x</think> {\"ok\": 1}"}}]})])
    assert sa._call_llm_uncached(client, "openrouter", "sys", "user", 100) == '{"ok": 1}'
    assert client.models == ["a/one:free", "b/two:free"] and sa._last_model["openrouter"] == "b/two:free"


def test_openrouter_joins_the_router_only_with_a_key(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENCODE_API_KEY", "OLLAMA_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert sa._get_llm_client()[1] == "groq"
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    client, provider = sa._get_llm_client()
    assert provider == "router" and [p for _, p in client.providers] == ["groq", "openrouter"]
