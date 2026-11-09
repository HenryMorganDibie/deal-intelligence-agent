"""Account emails, written by Deal Intelligence and sent through SendByte.

Supabase Auth keeps accounts, passwords, sessions and two-factor sign-in. Every email it would send (confirm your
email, reset your password, change of email, sign-in codes, security alerts) is instead handed to this module
through Supabase's Send Email hook, signed with the Standard Webhooks scheme. The email is rendered here in the
product's own design and sent with SendByte's API.

Links point to deal-intelligence.app/auth/confirm, never to a supabase.co address, and that page verifies only
when the reader presses its button: mail security scanners that open every link cannot use up a one-time link.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import os
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

TOLERANCE_SECONDS = 5 * 60
SUPPORT_EMAIL = "info@deal-intelligence.app"
BRAND = "Deal Intelligence"


class SignatureError(ValueError):
    """The request was not signed by Supabase with the configured secret."""


def hook_secrets() -> list[bytes]:
    """Signing keys from SEND_EMAIL_HOOK_SECRET ("v1,whsec_<base64>", several separated by | while rotating)."""
    keys = []
    for part in os.environ.get("SEND_EMAIL_HOOK_SECRET", "").split("|"):
        part = part.strip()
        if part.startswith("v1,whsec_"):
            part = part[len("v1,whsec_"):]
        elif part.startswith("whsec_"):
            part = part[len("whsec_"):]
        if not part:
            continue
        try:
            # Strict: a mis-pasted secret must read as missing, not as a key that never matches.
            keys.append(base64.b64decode(part, validate=True))
        except ValueError:
            continue
    return keys


def verify_signature(body: bytes, headers: dict, secrets: list[bytes], now: Optional[float] = None) -> None:
    """Standard Webhooks verification: HMAC-SHA256 of "<id>.<timestamp>.<body>", a recent timestamp, and a
    constant-time comparison against every signature in the header. Raises SignatureError."""
    if not secrets:
        raise SignatureError("not configured")
    msg_id = headers.get("webhook-id") or ""
    stamp = headers.get("webhook-timestamp") or ""
    signatures = headers.get("webhook-signature") or ""
    if not (msg_id and stamp and signatures):
        raise SignatureError("missing signature headers")
    try:
        sent = int(stamp)
    except ValueError:
        raise SignatureError("bad timestamp")
    if abs((now or time.time()) - sent) > TOLERANCE_SECONDS:
        raise SignatureError("timestamp outside tolerance")
    content = f"{msg_id}.{stamp}.".encode() + body
    expected = [base64.b64encode(hmac.new(key, content, hashlib.sha256).digest()).decode() for key in secrets]
    for item in signatures.split():
        version, _, sig = item.partition(",")
        if version == "v1" and any(hmac.compare_digest(sig, exp) for exp in expected):
            return
    raise SignatureError("signature mismatch")


# ── Rendering ─────────────────────────────────────────────────────────────────

def app_url() -> str:
    return (os.environ.get("DEAL_INTEL_APP_URL") or "https://deal-intelligence.app").rstrip("/")


def confirm_link(token_hash: str, kind: str) -> str:
    return f"{app_url()}/auth/confirm?{urlencode({'token_hash': token_hash, 'type': kind})}"


def _name(user: dict) -> Optional[str]:
    meta = user.get("user_metadata") or {}
    name = meta.get("display_name") or meta.get("full_name") or meta.get("name") or meta.get("username")
    return str(name).strip()[:60] if name else None


def _layout(*, preheader: str, heading: str, greeting: Optional[str], paragraphs: list[str],
            button: Optional[tuple[str, str]] = None, code: Optional[str] = None, note: Optional[str] = None,
            alert: bool = False) -> str:
    """One email in the product's design: table layout and inline styles, which every mail client renders."""
    e = html.escape
    accent = "#b42318" if alert else "#0f172a"
    parts = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light only"><title>' + e(heading) + "</title></head>"
        '<body style="margin:0;padding:0;background:#f4f5f7;">'
        '<div style="display:none;max-height:0;overflow:hidden;opacity:0;">' + e(preheader) + "</div>"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f5f7;">'
        '<tr><td align="center" style="padding:32px 16px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;">'
        '<tr><td style="padding:0 4px 18px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'font-size:15px;font-weight:700;letter-spacing:-0.01em;color:#0f172a;">' + e(BRAND) + "</td></tr>"
        '<tr><td style="background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;padding:32px 28px;'
        'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0f172a;line-height:1.55;">'
        f'<h1 style="margin:0 0 16px;font-size:21px;line-height:1.3;color:{accent};">' + e(heading) + "</h1>"
    ]
    if greeting:
        parts.append('<p style="margin:0 0 12px;font-size:15px;">' + e(greeting) + "</p>")
    for p in paragraphs:
        parts.append('<p style="margin:0 0 12px;font-size:15px;color:#334155;">' + p + "</p>")
    if code:
        parts.append(
            '<p style="margin:20px 0;"><span style="display:inline-block;padding:12px 18px;border-radius:8px;'
            'background:#f1f5f9;border:1px solid #e2e8f0;font-family:SFMono-Regular,Menlo,Consolas,monospace;'
            'font-size:26px;letter-spacing:6px;font-weight:700;color:#0f172a;">' + e(code) + "</span></p>")
    if button:
        label, url = button
        parts.append(
            '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:22px 0 18px;"><tr>'
            f'<td style="border-radius:8px;background:{accent};">'
            f'<a href="{e(url)}" style="display:inline-block;padding:12px 22px;font-size:15px;font-weight:600;'
            'color:#ffffff;text-decoration:none;border-radius:8px;">' + e(label) + "</a></td></tr></table>"
            '<p style="margin:0 0 12px;font-size:13px;color:#64748b;">If the button does not work, copy this '
            f'link into your browser:<br><a href="{e(url)}" style="color:#475569;word-break:break-all;">'
            + e(url) + "</a></p>")
    if note:
        parts.append('<p style="margin:16px 0 0;padding-top:14px;border-top:1px solid #eef0f3;font-size:13px;'
                     'color:#64748b;">' + note + "</p>")
    parts.append(
        "</td></tr>"
        '<tr><td style="padding:18px 4px 0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        'font-size:12px;line-height:1.5;color:#94a3b8;">'
        f"{e(BRAND)} · African deals, markets and risk · "
        f'<a href="{e(app_url())}" style="color:#94a3b8;">deal-intelligence.app</a><br>'
        f'Questions? Reply to this email or write to <a href="mailto:{SUPPORT_EMAIL}" style="color:#94a3b8;">'
        f"{SUPPORT_EMAIL}</a>. We will never ask for your password."
        "</td></tr></table></td></tr></table></body></html>")
    return "".join(parts)


def _text(heading: str, greeting: Optional[str], lines: list[str], button: Optional[tuple[str, str]] = None,
          code: Optional[str] = None, note: Optional[str] = None) -> str:
    out = [heading, ""]
    if greeting:
        out += [greeting, ""]
    out += [html.unescape(_strip(line)) for line in lines]
    if code:
        out += ["", f"    {code}", ""]
    if button:
        out += ["", f"{button[0]}: {button[1]}", ""]
    if note:
        out += ["", html.unescape(_strip(note))]
    out += ["", "--", f"{BRAND} · {app_url()}", f"Questions? Write to {SUPPORT_EMAIL}. We will never ask for your password."]
    return "\n".join(out)


def _strip(fragment: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", fragment)


def _when() -> str:
    return datetime.now(timezone.utc).strftime("%d %B %Y at %H:%M UTC")


def render(kind: str, user: dict, data: dict, recipient_role: str = "current") -> tuple[str, str, str]:
    """(subject, html, text) for one email. recipient_role is "current" or "new" for a change of email."""
    e = html.escape
    name = _name(user)
    greeting = f"Hello {name}," if name else "Hello,"
    ignore = "If you did not ask for this, you can ignore this email: nothing will change."
    secure = (f'If this was not you, <a href="{e(app_url())}/account" style="color:#b42318;">reset your password'
              f"</a> now and write to {SUPPORT_EMAIL}.")
    email = e(user.get("email") or "")
    new_email = e(user.get("new_email") or "")
    token, token_new = data.get("token") or "", data.get("token_new") or ""
    hash_, hash_new = data.get("token_hash") or "", data.get("token_hash_new") or ""

    def build(subject, heading, paras, *, button=None, code=None, note=None, alert=False, preheader=None):
        body = _layout(preheader=preheader or heading, heading=heading, greeting=greeting, paragraphs=paras,
                       button=button, code=code, note=note, alert=alert)
        return subject, body, _text(heading, greeting, paras, button, code, note)

    if kind == "signup":
        return build("Confirm your email for Deal Intelligence", "Confirm your email address",
                     [f"Thanks for creating a {BRAND} account. Confirm that <strong>{email}</strong> is yours to "
                      "finish signing up."],
                     button=("Confirm email address", confirm_link(hash_, "signup")),
                     note="This link works once and expires soon. " + ignore,
                     preheader="One click to finish creating your account.")
    if kind == "invite":
        return build(f"You have been invited to {BRAND}", f"You have been invited to {BRAND}",
                     [f"{BRAND} tracks private deals, listed markets, government securities and risk across all 54 "
                      "African countries. Accept the invitation to set up your account."],
                     button=("Accept invitation", confirm_link(hash_, "invite")), note=ignore)
    if kind == "magiclink":
        return build(f"Your {BRAND} sign-in link", "Sign in to Deal Intelligence",
                     ["Use the button below to sign in. The link works once and expires soon."],
                     button=("Sign in", confirm_link(hash_, "magiclink")),
                     note="If you did not try to sign in, ignore this email. " + secure)
    if kind == "recovery":
        return build(f"Reset your {BRAND} password", "Reset your password",
                     [f"We received a request to reset the password for <strong>{email}</strong>. Choose a new "
                      "password with the button below."],
                     button=("Choose a new password", confirm_link(hash_, "recovery")),
                     note="This link works once and expires soon. If you did not ask for a reset, ignore this "
                          "email: your password stays the same.",
                     preheader="Choose a new password for your account.")
    if kind == "email_change":
        if recipient_role == "new":
            link_hash = hash_ if (hash_ and hash_new) else (hash_ or hash_new)
            return build(f"Confirm your new {BRAND} email", "Confirm your new email address",
                         [f"Confirm <strong>{new_email or email}</strong> as the email address for your "
                          f"{BRAND} account."],
                         button=("Confirm new email", confirm_link(link_hash, "email_change")),
                         note=ignore)
        return build(f"Confirm the change of your {BRAND} email", "Confirm the change of your email address",
                     [f"Someone asked to change your account's email from <strong>{email}</strong> to "
                      f"<strong>{new_email}</strong>. The change happens only when both addresses confirm."],
                     button=("Confirm the change", confirm_link(hash_new, "email_change")),
                     note="If you did not ask for this, do not press the button. " + secure, alert=True)
    if kind == "email":
        return build(f"{token} is your {BRAND} sign-in code", "Your sign-in code",
                     ["Enter this code to sign in. It works once and expires soon."], code=token,
                     note="If you did not try to sign in, ignore this email. " + secure)
    if kind == "reauthentication":
        return build(f"{token} is your {BRAND} verification code", "Confirm it is you",
                     ["Enter this code to confirm a sensitive change to your account. It expires soon."], code=token,
                     note="If you are not changing your account, ignore this email. " + secure)
    notices = {
        "password_changed_notification": ("Your password was changed", "Your password was changed",
                                          [f"The password for <strong>{email}</strong> was changed on {_when()}."]),
        "email_changed_notification": ("Your email address was changed", "Your email address was changed",
                                       [f"Your account's email address was changed from <strong>{e(data.get('old_email') or '')}"
                                        f"</strong> to <strong>{email}</strong> on {_when()}."]),
        "phone_changed_notification": ("Your phone number was changed", "Your phone number was changed",
                                       [f"The phone number on your account was changed on {_when()}."]),
        "identity_linked_notification": ("A sign-in method was added", "A sign-in method was added",
                                         [f"{e((data.get('provider') or 'A new provider').title())} was linked to your "
                                          f"account on {_when()}. You can now sign in with it."]),
        "identity_unlinked_notification": ("A sign-in method was removed", "A sign-in method was removed",
                                           [f"{e((data.get('provider') or 'A provider').title())} was removed from your "
                                            f"account on {_when()}."]),
        "mfa_factor_enrolled_notification": ("Two-factor sign-in was turned on", "Two-factor sign-in is on",
                                             [f"An authenticator app was added to your account on {_when()}. Signing "
                                              "in now needs a code from it as well as your password."]),
        "mfa_factor_unenrolled_notification": ("Two-factor sign-in was turned off", "Two-factor sign-in was turned off",
                                               [f"An authenticator app was removed from your account on {_when()}. "
                                                "Signing in now needs only your password."]),
    }
    subject, heading, paras = notices.get(kind, ("Security notice for your account", "Security notice",
                                                 [f"There was a change to your account on {_when()}."]))
    return build(f"{BRAND}: {subject.lower() if subject[0].isupper() else subject}", heading, paras,
                 note=secure, alert=True,
                 button=("Review your security settings", f"{app_url()}/account/security"))


def messages(payload: dict) -> list[dict]:
    """Every email one hook call asks for: [{"to", "subject", "html", "text", "kind"}]. A change of email with
    Secure Email Change on sends two; a change-of-email notice goes to the old address."""
    user = payload.get("user") or {}
    data = payload.get("email_data") or {}
    kind = str(data.get("email_action_type") or "")
    out = []

    def add(to: Optional[str], role: str = "current") -> None:
        if to:
            subject, body, text = render(kind, user, data, role)
            out.append({"to": to, "subject": subject, "html": body, "text": text, "kind": kind, "role": role})

    if kind == "email_change":
        if data.get("token_hash") and data.get("token_hash_new"):
            add(user.get("email"), "current")             # token_hash_new goes to the current address
            add(user.get("new_email"), "new")             # token_hash goes to the new address
        else:
            add(user.get("new_email") or user.get("email"), "new")
    elif kind == "email_changed_notification":
        add(data.get("old_email") or user.get("email"))
    else:
        add(user.get("email"))
    return out


def sender() -> str:
    return os.environ.get("AUTH_EMAIL_FROM", f"{BRAND} <account@deal-intelligence.app>").strip()


def idempotency_key(webhook_id: str, to: str, role: str) -> str:
    """One send per hook delivery and recipient: Supabase retrying a delivery never sends a second email."""
    return "di-auth-" + hashlib.sha256(f"{webhook_id}|{to.lower()}|{role}".encode()).hexdigest()[:48]
