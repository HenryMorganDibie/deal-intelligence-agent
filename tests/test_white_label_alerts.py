"""White-label election alerts: no product name or links in what the subscriber receives."""
import json

from src import election_alerts
from src.engines import chat_formats

STORY = {"id": "s1", "title": "Ballot snatching reported in Ikeja", "url": "https://news.example/a", "severity": "high",
         "incident_type": "violence", "states": ["Lagos"], "lgas": ["Ikeja, Lagos"], "outlets": ["Example News"],
         "published": "2027-01-16T10:00:00Z"}


def _payload(url, white):
    sub = {"id": "a1", "name": "Lagos incidents", "webhook_url": url, "filters": {"white_label": white}}
    return json.dumps(election_alerts._payload(sub, [STORY]))


def test_white_label_alerts_carry_no_brand_or_product_links():
    for url in ("https://hooks.slack.com/services/T/B/X", "https://discord.com/api/webhooks/1/x",
                "https://chat.googleapis.com/v1/spaces/x/messages?key=k", "https://x.webhook.office.com/abc",
                "https://client.example/hook"):
        body = _payload(url, True)
        assert chat_formats.BRAND not in body and "deal-intelligence" not in body, url
        assert "Ballot snatching" in body


def test_branded_alerts_are_unchanged_by_default():
    assert chat_formats.BRAND in _payload("https://hooks.slack.com/services/T/B/X", False)
    assert election_alerts.clean_filters({"white_label": True})["white_label"] is True
    assert "white_label" not in election_alerts.clean_filters({})


def _email(white, monkeypatch):
    monkeypatch.setattr(election_alerts, "unsubscribe_link", lambda sub_id: "https://api.example/stop?id=a1")
    sub = {"id": "a1", "name": "Lagos incidents", "filters": {"white_label": white}}
    subject, html, text = election_alerts.render_email(sub, [STORY])
    return subject + html + text


def test_white_label_email_has_no_brand_header_footer_or_app_links(monkeypatch):
    body = _email(True, monkeypatch)
    assert chat_formats.BRAND not in body and "deal-intelligence" not in body
    assert "Ballot snatching" in body and "https://api.example/stop?id=a1" in body   # the stop link is kept


def test_branded_email_keeps_header_and_manage_link(monkeypatch):
    body = _email(False, monkeypatch)
    assert "Manage election alerts" in body and "deal-intelligence" in body
