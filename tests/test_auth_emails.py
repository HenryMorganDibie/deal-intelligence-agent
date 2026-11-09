import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from src.engines import auth_emails as ae

KEY = base64.b64encode(b"k" * 32).decode()
SECRET = f"v1,whsec_{KEY}"
USER = {"id": "u1", "email": "ada@example.com", "new_email": "ada@new.example",
        "user_metadata": {"display_name": "Ada", "username": "ada_l"}}


def sign(body: bytes, key: str = KEY, msg_id: str = "msg_1", stamp=None) -> dict:
    stamp = str(int(stamp if stamp is not None else time.time()))
    sig = base64.b64encode(hmac.new(base64.b64decode(key), f"{msg_id}.{stamp}.".encode() + body,
                                    hashlib.sha256).digest()).decode()
    return {"webhook-id": msg_id, "webhook-timestamp": stamp, "webhook-signature": f"v1,{sig}"}


def test_signature_accepts_valid_and_rejects_tampered_old_or_foreign(monkeypatch):
    monkeypatch.setenv("SEND_EMAIL_HOOK_SECRET", SECRET)
    keys, body = ae.hook_secrets(), b'{"a":1}'
    ae.verify_signature(body, sign(body), keys)
    with pytest.raises(ae.SignatureError):
        ae.verify_signature(b'{"a":2}', sign(body), keys)
    with pytest.raises(ae.SignatureError):
        ae.verify_signature(body, sign(body, stamp=time.time() - 3600), keys)
    with pytest.raises(ae.SignatureError):
        ae.verify_signature(body, sign(body, key=base64.b64encode(b"x" * 32).decode()), keys)
    with pytest.raises(ae.SignatureError):
        ae.verify_signature(body, {}, keys)
    with pytest.raises(ae.SignatureError):
        ae.verify_signature(body, sign(body), [])                    # never accept when unconfigured


def test_rotation_accepts_either_secret(monkeypatch):
    old = base64.b64encode(b"o" * 32).decode()
    monkeypatch.setenv("SEND_EMAIL_HOOK_SECRET", f"v1,whsec_{KEY}|v1,whsec_{old}")
    ae.verify_signature(b"{}", sign(b"{}", key=old), ae.hook_secrets())


@pytest.mark.parametrize("kind", ["signup", "invite", "magiclink", "recovery", "email", "reauthentication",
                                  "password_changed_notification", "email_changed_notification",
                                  "identity_linked_notification", "mfa_factor_enrolled_notification",
                                  "mfa_factor_unenrolled_notification", "something_new"])
def test_every_kind_renders_branded_and_safe(kind):
    data = {"email_action_type": kind, "token": "123456", "token_hash": "a" * 56, "old_email": "old@example.com",
            "provider": "google"}
    subject, body, text = ae.render(kind, {**USER, "user_metadata": {"display_name": "<b>Ada</b>"}}, data)
    assert "Deal Intelligence" in subject and "Deal Intelligence" in body and "<b>Ada</b>" not in body
    assert "supabase" not in body.lower() and "supabase" not in text.lower()
    assert "never ask for your password" in text


def test_links_point_to_our_confirm_page():
    _, body, text = ae.render("recovery", USER, {"email_action_type": "recovery", "token_hash": "b" * 56})
    link = "https://deal-intelligence.app/auth/confirm?token_hash=" + "b" * 56 + "&amp;type=recovery"
    assert link in body and link.replace("&amp;", "&") in text


def test_secure_email_change_sends_two_emails_with_the_documented_mapping():
    payload = {"user": USER, "email_data": {"email_action_type": "email_change", "token": "111111",
                                            "token_hash": "n" * 56, "token_new": "222222", "token_hash_new": "c" * 56}}
    msgs = ae.messages(payload)
    assert [(m["to"], m["role"]) for m in msgs] == [("ada@example.com", "current"), ("ada@new.example", "new")]
    assert "c" * 56 in msgs[0]["html"] and "n" * 56 in msgs[1]["html"]   # token_hash_new -> current address


def test_single_email_change_goes_to_the_new_address_and_notice_to_the_old():
    single = ae.messages({"user": USER, "email_data": {"email_action_type": "email_change", "token_hash": "n" * 56}})
    assert [m["to"] for m in single] == ["ada@new.example"]
    notice = ae.messages({"user": USER, "email_data": {"email_action_type": "email_changed_notification",
                                                       "old_email": "old@example.com"}})
    assert [m["to"] for m in notice] == ["old@example.com"]


def test_idempotency_key_is_per_delivery_and_recipient():
    assert ae.idempotency_key("m1", "A@x.com", "current") == ae.idempotency_key("m1", "a@x.com", "current")
    assert ae.idempotency_key("m1", "a@x.com", "current") != ae.idempotency_key("m2", "a@x.com", "current")


def test_hook_endpoint(monkeypatch):
    import api.index as api
    import src.hosted_market as hm
    monkeypatch.setenv("SEND_EMAIL_HOOK_SECRET", SECRET)
    monkeypatch.setenv("SENDBYTE_API_KEY", "test")
    sent = []

    async def fake_send(client, to, subject, html_body, text_body, unsubscribe, key, **kw):
        sent.append((to, subject, unsubscribe, kw["tags"]))
        return {"sent": True, "status": 201, "error": None}
    monkeypatch.setattr(hm.email_alerts, "send", fake_send)
    client = TestClient(api.app)
    body = json.dumps({"user": USER, "email_data": {"email_action_type": "signup", "token_hash": "d" * 56}}).encode()
    assert client.post("/api/auth/send-email", content=body, headers={"x-forwarded-for": "1.2.3.4"}).status_code == 401
    r = client.post("/api/auth/send-email", content=body, headers=sign(body))
    assert r.status_code == 200 and r.json() == {}
    assert sent == [("ada@example.com", "Confirm your email for Deal Intelligence", None, ["account", "signup"])]
    status = client.get("/api/auth/send-email").json()
    assert status == {"hook_secret": True, "sendbyte": True, "ready": True,
                      "sender": "Deal Intelligence <account@deal-intelligence.app>"}


def test_hook_reports_a_failed_send(monkeypatch):
    import api.index as api
    import src.hosted_market as hm
    monkeypatch.setenv("SEND_EMAIL_HOOK_SECRET", SECRET)
    monkeypatch.setenv("SENDBYTE_API_KEY", "test")

    async def failing(*a, **kw):
        return {"sent": False, "status": 500, "error": "http_500"}
    monkeypatch.setattr(hm.email_alerts, "send", failing)
    body = json.dumps({"user": USER, "email_data": {"email_action_type": "recovery", "token_hash": "e" * 56}}).encode()
    r = TestClient(api.app).post("/api/auth/send-email", content=body, headers=sign(body))
    assert r.status_code == 502 and "could not be sent" in r.json()["error"]["message"]


def test_mis_pasted_hook_secret_reads_as_missing(monkeypatch):
    monkeypatch.setenv("SEND_EMAIL_HOOK_SECRET", "v1,whsec_not base64 at all!")
    assert ae.hook_secrets() == []
