import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

import api.index as api
from src import request_identity as rid

WEB = "web-secret-value"
SERVER = "server-secret-value"


@pytest.fixture
def locked(monkeypatch):
    monkeypatch.setenv("DEAL_INTEL_WEB_SECRET", WEB)
    monkeypatch.setenv("DEAL_INTEL_API_SECRET", SERVER)
    return TestClient(api.app)


def test_without_the_web_secret_nothing_is_locked(monkeypatch):
    monkeypatch.delenv("DEAL_INTEL_WEB_SECRET", raising=False)
    assert TestClient(api.app).get("/api/does-not-exist").status_code == 404


def test_internal_routes_refuse_callers_without_a_secret(locked):
    r = locked.get("/api/deals")
    assert r.status_code == 403 and "developers" in r.json()["detail"] and r.headers["cache-control"] == "no-store"
    assert locked.get("/api/deals", headers={rid.CLIENT_HEADER: "wrong"}).status_code == 403


@pytest.mark.parametrize("secret", [WEB, SERVER])
def test_the_app_and_the_scheduled_jobs_get_through(locked, secret):
    r = locked.get("/api/does-not-exist", headers={rid.CLIENT_HEADER: secret})
    assert r.status_code == 404                     # reached the app, which has no such route
    assert "x-deal-intel-client" in r.headers.get("vary", "").lower()


@pytest.mark.parametrize("path", ["/v1", "/api/health", "/robots.txt", "/api/watchlists/email/unsubscribe",
                                  "/api/watchlists/00000000-0000-0000-0000-000000000000/feed.xml",
                                  "/api/cron/ingest", "/api/auth/send-email"])
def test_routes_other_services_reach_directly_stay_open(locked, path):
    assert locked.get(path).status_code != 403


def test_preflight_is_not_blocked(locked):
    r = locked.options("/api/deals", headers={"Origin": "https://deal-intelligence.app",
                                               "Access-Control-Request-Method": "GET"})
    assert r.status_code != 403


def _request(headers: dict) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": ("10.0.0.1", 1234), "method": "GET", "path": "/"})


def test_visitor_address_is_believed_only_with_the_secret(monkeypatch):
    monkeypatch.setenv("DEAL_INTEL_WEB_SECRET", WEB)
    spoof = {rid.CLIENT_IP_HEADER: "203.0.113.9", "x-forwarded-for": "198.51.100.4"}
    assert rid.caller_ip(_request(spoof)) == "198.51.100.4"
    assert rid.caller_ip(_request({**spoof, rid.CLIENT_HEADER: WEB})) == "203.0.113.9"
    assert rid.caller_ip(_request({rid.CLIENT_HEADER: WEB, rid.CLIENT_IP_HEADER: "not-an-ip",
                                   "x-forwarded-for": "198.51.100.4"})) == "198.51.100.4"
