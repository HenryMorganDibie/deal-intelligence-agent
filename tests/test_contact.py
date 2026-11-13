"""Requests from the page go to the team's inbox, with the account's confirmed email as reply-to."""
import asyncio

import pytest
from fastapi import HTTPException

from src import contact
from src.engines import email_alerts


def test_request_goes_to_the_inbox_with_the_account_as_reply_to(monkeypatch):
    sent = []

    async def fake_send(client, to, subject, page, text, unsub, key, **kw):
        sent.append((to, subject, text, kw))
        return {"sent": True, "status": 200, "error": None}
    monkeypatch.setattr(email_alerts, "send", fake_send)
    monkeypatch.setattr(contact, "_account_email", lambda owner: "buyer@example.org")
    contact._recent.clear()
    body = contact.ContactIn(topic="election_coverage", message="We need Angola incidents from June.",
                             organisation="Acme Research", subject_detail="Angola, August 2027")
    out = asyncio.run(contact.submit("user-1", "pro", body))
    to, subject, text, kw = sent[0]
    assert out == {"sent": True, "reply_to": "buyer@example.org"}
    assert to == contact.inbox() and kw["reply_to_address"] == "buyer@example.org"
    assert subject == "[Request] Election coverage request: Angola, August 2027"
    assert "Acme Research" in text and "Plan: pro" in text and "<" not in text


def test_requests_are_limited_per_account_and_failures_are_reported(monkeypatch):
    async def ok(*a, **k):
        return {"sent": True, "status": 200, "error": None}
    monkeypatch.setattr(email_alerts, "send", ok)
    monkeypatch.setattr(contact, "_account_email", lambda owner: None)
    contact._recent.clear()
    body = contact.ContactIn(message="Please tell me about Institutional.")
    for _ in range(3):
        asyncio.run(contact.submit("user-2", "free", body))
    with pytest.raises(HTTPException) as e:
        asyncio.run(contact.submit("user-2", "free", body))
    assert e.value.status_code == 429

    async def fail(*a, **k):
        return {"sent": False, "status": 500, "error": "http_500"}
    monkeypatch.setattr(email_alerts, "send", fail)
    with pytest.raises(HTTPException) as e:
        asyncio.run(contact.submit("user-3", "free", body))
    assert e.value.status_code == 503 and "user-3" not in contact._recent


def test_signed_out_visitors_give_a_valid_name_and_email(monkeypatch):
    sent = []

    async def fake_send(client, to, subject, page, text, unsub, key, **kw):
        sent.append((to, subject, text, kw))
        return {"sent": True, "status": 200, "error": None}
    monkeypatch.setattr(email_alerts, "send", fake_send)
    contact._recent.clear()
    contact._public.clear()
    with pytest.raises(HTTPException):
        asyncio.run(contact.submit(None, "none", contact.ContactIn(message="Demo please, next week.", email="a@b.co"), "1.1.1.1"))
    with pytest.raises(HTTPException):
        asyncio.run(contact.submit(None, "none", contact.ContactIn(message="Demo please, next week.", name="Ada",
                                                                    email="not-an-email"), "1.1.1.1"))
    body = contact.ContactIn(topic="demo", message="Demo please, next week.", name="Ada Obi", email="ada@fund.example",
                             elapsed_ms=20000)
    out = asyncio.run(contact.submit(None, "none", body, "1.1.1.1"))
    to, subject, text, kw = sent[0]
    assert out["reply_to"] == "ada@fund.example" and kw["reply_to_address"] == "ada@fund.example"
    assert to == contact.inbox() and subject == "[Request] Demonstration request"
    assert "Ada Obi <ada@fund.example>" in text and "not signed in" in text


def test_bots_are_accepted_quietly_and_public_requests_are_capped(monkeypatch):
    sent = []

    async def fake_send(*a, **k):
        sent.append(a)
        return {"sent": True, "status": 200, "error": None}
    monkeypatch.setattr(email_alerts, "send", fake_send)
    contact._recent.clear()
    contact._public.clear()
    base = dict(message="Tell me about pricing.", name="Bot", email="bot@spam.example")
    assert asyncio.run(contact.submit(None, "none", contact.ContactIn(**base, website="http://x"), "2.2.2.2"))["sent"]
    assert asyncio.run(contact.submit(None, "none", contact.ContactIn(**base, elapsed_ms=500), "3.3.3.3"))["sent"]
    assert sent == []
    monkeypatch.setattr(contact, "_PUBLIC_HOURLY", 2)
    for ip in ("4.4.4.4", "5.5.5.5"):
        asyncio.run(contact.submit(None, "none", contact.ContactIn(**base, elapsed_ms=9000), ip))
    with pytest.raises(HTTPException) as e:
        asyncio.run(contact.submit(None, "none", contact.ContactIn(**base, elapsed_ms=9000), "6.6.6.6"))
    assert e.value.status_code == 429 and len(sent) == 2
