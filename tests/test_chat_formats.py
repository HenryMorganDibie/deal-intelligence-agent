import json

import pytest
from fastapi.testclient import TestClient

from src.engines import chat_formats as cf

WL = {"id": "w1", "name": "Nigerian fintech"}
LINK = "https://deal-intelligence.app/app/watchlists/w1"
ALERTS = [{"kind": "deal", "id": str(i), "day": "2026-11-09", "title": f"Moniepoint raises round {i} <&>",
           "deal_type": "equity_funding", "amount_usd": 110_000_000, "publisher": "TechCabal",
           "url": f"https://example.com/{i}"} for i in range(11)]


@pytest.mark.parametrize("url,kind", [
    ("https://hooks.slack.com/services/T0/B0/xyz", "slack"),
    ("https://discord.com/api/webhooks/1/abc", "discord"),
    ("https://chat.googleapis.com/v1/spaces/AAA/messages?key=k&token=t", "google_chat"),
    ("https://prod-12.westus.logic.azure.com:443/workflows/abc/triggers/manual/paths/invoke?sig=x", "teams"),
    ("https://default123.ab.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/x", "teams"),
    ("https://contoso.webhook.office.com/webhookb2/abc", "teams"),
    ("https://hooks.zapier.com/hooks/catch/1/abc", "json"),
    ("https://discord.com/channels/1/2", "json"),
    ("https://evilhooks.slack.com.example.org/x", "json"),
    (None, "json"),
])
def test_destination_is_recognised_from_the_url(url, kind):
    assert cf.destination(url) == kind


def test_slack_message_escapes_and_caps():
    m = cf.slack(WL, ALERTS, LINK)
    assert m["text"] == "11 new alerts for Nigerian fintech"
    sections = [b for b in m["blocks"] if b["type"] == "section"]
    assert len(sections) == cf.MAX_SHOWN
    assert "<https://example.com/0|Moniepoint raises round 0 &lt;&amp;&gt;>" in sections[0]["text"]["text"]
    assert "Deal · Equity funding · $110m · 9 Nov 2026 · TechCabal" in sections[0]["text"]["text"]
    button = next(b for b in m["blocks"] if b["type"] == "actions")["elements"][0]
    assert button["url"] == LINK and button["text"]["text"] == "Open watchlist (3 more)"
    assert len(m["blocks"]) <= 50


def test_teams_card_is_a_valid_adaptive_card_message():
    m = cf.teams(WL, ALERTS[:2], LINK)
    att = m["attachments"][0]
    assert m["type"] == "message" and att["contentType"] == "application/vnd.microsoft.card.adaptive"
    card = att["content"]
    assert card["type"] == "AdaptiveCard" and card["version"] == "1.4"
    assert card["actions"][0] == {"type": "Action.OpenUrl", "url": LINK, "title": "Open watchlist"}
    assert len(json.dumps(m)) < 28_000


def test_discord_never_pings_and_stays_within_limits():
    m = cf.discord(WL, ALERTS, LINK)
    assert m["allowed_mentions"] == {"parse": []} and len(m["embeds"]) <= 10 and len(m["content"]) < 2000


def test_google_chat_text_links():
    m = cf.google_chat(WL, ALERTS[:1], LINK)
    assert "• <https://example.com/0|Moniepoint raises round 0 (&)>" in m["text"]


def test_unknown_hosts_get_the_generic_payload():
    generic = {"watchlist": {}, "alerts": []}
    assert cf.payload("https://example.org/hook", WL, ALERTS, LINK, generic) is generic


def test_updated_alerts_are_marked_and_bad_amounts_skipped():
    line = cf.facts({"kind": "event", "signal_type": "credit_risk", "day": "bad", "amount_usd": "x",
                     "change_type": "updated"})
    assert line == "Event · Credit risk · updated"


def test_test_endpoint_formats_for_the_destination(monkeypatch):
    import api.index as api
    from src import hosted_market as hm
    sent = {}

    async def fake_deliver(url, payload, key):
        sent.update(url=url, payload=payload, key=key)
        return {"delivered": True, "attempts": 1, "status_code": 200, "error": None}
    monkeypatch.setattr(hm.watch, "deliver_webhook", fake_deliver)
    monkeypatch.setattr(hm, "_public_host", lambda url: True)
    hm._webhook_tests.clear()
    client = TestClient(api.app)
    r = client.post("/api/webhooks/test", json={"url": "https://hooks.slack.com/services/T/B/x", "name": "Fintech"})
    assert r.json() == {"delivered": True, "destination": "slack", "label": "Slack", "status_code": 200, "error": None}
    assert sent["payload"]["text"] == "2 new alerts for Fintech" and sent["key"].startswith("deal-intel-test-")
    assert client.post("/api/webhooks/test", json={"url": "http://hooks.slack.com/x"}).status_code == 422
    codes = [client.post("/api/webhooks/test", json={"url": "https://example.org/h"}).status_code for _ in range(5)]
    assert codes[-1] == 429
