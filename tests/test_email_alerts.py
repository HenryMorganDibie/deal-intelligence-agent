import asyncio

import httpx

from src.engines import email_alerts

TOKEN = "a" * 64
ALERT = {"kind": "event", "id": "e1", "day": "2026-11-02", "title": "Acme <raises> $5m",
         "signal_type": "funding", "publisher": "TechCabal", "url": "https://example.com/acme"}


def test_render_escapes_and_links_unsubscribe():
    subject, body, text = email_alerts.render({"name": "Fintech <NG>"}, [ALERT], "https://app/wl/1",
                                              email_alerts.unsubscribe_link(TOKEN), "Ada")
    assert subject == "1 new match on Fintech <NG>"
    assert "&lt;raises&gt;" in body and "<raises>" not in body
    assert "Fintech &lt;NG&gt;" in body
    assert f"token={TOKEN}" in body and f"token={TOKEN}" in text
    assert "Hello Ada," in text and "https://example.com/acme" in text


def test_render_caps_long_batches():
    alerts = [{**ALERT, "id": str(i)} for i in range(email_alerts.MAX_ALERTS_IN_EMAIL + 5)]
    subject, body, text = email_alerts.render({"name": "W"}, alerts, "https://app", "https://u")
    assert subject.startswith(f"{len(alerts)} new matches")
    assert "and 5 more" in body and "...and 5 more." in text


def test_non_https_source_is_not_linked():
    _, body, _ = email_alerts.render({"name": "W"}, [{**ALERT, "url": "javascript:alert(1)"}], "https://app", "https://u")
    assert "javascript:" not in body


def test_idempotency_key_is_per_subscriber_and_stable():
    a = email_alerts.idempotency_key("batch", TOKEN)
    assert a == email_alerts.idempotency_key("batch", TOKEN)
    assert a != email_alerts.idempotency_key("batch", "b" * 64)
    assert len(a) <= 256


def test_send_without_key_reports_not_configured(monkeypatch):
    monkeypatch.delenv("SENDBYTE_API_KEY", raising=False)

    async def run():
        async with httpx.AsyncClient() as client:
            return await email_alerts.send(client, "x@example.com", "s", "<p>h</p>", "t", "https://u", "k")
    assert asyncio.run(run()) == {"sent": False, "status": None, "error": "email_not_configured"}


def test_send_posts_one_click_unsubscribe_headers(monkeypatch):
    monkeypatch.setenv("SENDBYTE_API_KEY", "test-key")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": "m1"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await email_alerts.send(client, "x@example.com", "s", "<p>h</p>", "t", "https://u", "k1")
    assert asyncio.run(run())["sent"] is True
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["headers"]["List-Unsubscribe"] == "<https://u>"
    assert seen["body"]["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert seen["body"]["idempotency_key"] == "k1" and seen["body"]["to"] == ["x@example.com"]
