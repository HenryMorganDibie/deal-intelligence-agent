from fastapi.testclient import TestClient

import api.index as api


def test_requests_over_the_per_ip_limit_get_429(monkeypatch):
    monkeypatch.setattr(api, "IP_PER_MINUTE", 3)
    api._ip_window.clear()
    client = TestClient(api.app)
    headers = {"x-forwarded-for": "203.0.113.7"}
    codes = [client.get("/robots.txt", headers=headers).status_code for _ in range(5)]
    assert codes == [200] * 5                                   # robots.txt is never limited
    codes = [client.get("/api/does-not-exist", headers=headers).status_code for _ in range(5)]
    assert codes[:3] == [404, 404, 404] and codes[3:] == [429, 429]
    blocked = client.get("/api/does-not-exist", headers=headers)
    assert blocked.headers["retry-after"] == "60" and blocked.headers["cache-control"] == "no-store"
    # Another address is unaffected.
    assert client.get("/api/does-not-exist", headers={"x-forwarded-for": "198.51.100.2"}).status_code == 404


def test_scheduled_jobs_with_the_cron_secret_are_never_limited(monkeypatch):
    monkeypatch.setattr(api, "IP_PER_MINUTE", 1)
    monkeypatch.setattr(api, "CRON_SECRET", "job-secret")
    api._ip_window.clear()
    client = TestClient(api.app)
    headers = {"x-forwarded-for": "203.0.113.9", "authorization": "Bearer job-secret"}
    assert all(client.get("/api/does-not-exist", headers=headers).status_code == 404 for _ in range(4))


def test_the_window_resets_each_minute(monkeypatch):
    monkeypatch.setattr(api, "IP_PER_MINUTE", 2)
    api._ip_window.clear()
    assert [api._rate_limited("x", 60.0 * 10 + s) for s in (0, 1, 2)] == [False, False, True]
    assert api._rate_limited("x", 60.0 * 11) is False
