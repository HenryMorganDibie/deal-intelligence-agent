"""
Who is calling the API's internal /api/* routes, and from which address.

Those routes serve the web app. Trusted callers present a secret in X-Deal-Intel-Client:
  * the web app (DEAL_INTEL_WEB_SECRET), from its server and from its /api/data proxy;
  * the scheduled GitHub jobs and scripts (DEAL_INTEL_API_SECRET, which they already hold).
Everyone else uses the key-authenticated /v1.

Behind the web app's proxy every request would appear to come from Vercel, so the proxy passes the visitor's
address in X-Deal-Intel-Client-IP. That header is believed only together with a valid secret; otherwise the
connection's own forwarded address is used, so nobody can pick an address to dodge per-visitor limits.
"""
from __future__ import annotations

import hmac
import ipaddress
import os
import re

from starlette.requests import Request

CLIENT_HEADER = "x-deal-intel-client"
CLIENT_IP_HEADER = "x-deal-intel-client-ip"

# Routes other services must reach directly: they authenticate themselves or are meant to be public.
_OPEN = (
    re.compile(r"^/v1(/|$)"),                                  # customers' API: its own keys
    re.compile(r"^/api/auth/send-email$"),                     # Supabase hook: signed
    re.compile(r"^/api/cron/"),                                # scheduled jobs: their own secrets
    re.compile(r"^/api/health$"),
    re.compile(r"^/api/watchlists/email/unsubscribe$"),        # links in emails
    re.compile(r"^/api/watchlists/[0-9a-fA-F-]{36}/feed\.xml$"),  # RSS readers
    re.compile(r"^/robots\.txt$"),
)


def web_secret() -> str:
    return os.environ.get("DEAL_INTEL_WEB_SECRET", "")


def enforced() -> bool:
    """The lock is on once the web app's secret is configured (so a deploy can never lock the app out first)."""
    return bool(web_secret())


def is_open_path(path: str) -> bool:
    return not path.startswith("/api/") or any(p.match(path) for p in _OPEN)


def trusted(request: Request) -> bool:
    presented = request.headers.get(CLIENT_HEADER, "").strip()
    if not presented:
        return False
    for secret in (web_secret().strip(), os.environ.get("DEAL_INTEL_API_SECRET", "").strip()):
        if secret and hmac.compare_digest(presented.encode(), secret.encode()):
            return True
    return False


def caller_ip(request: Request) -> str:
    if trusted(request):
        claimed = request.headers.get(CLIENT_IP_HEADER, "").strip()
        try:
            return str(ipaddress.ip_address(claimed))
        except ValueError:
            pass
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
