import time

import httpx

import src.hosted_market as hm


class FakeStore:
    def __init__(self, rows, changed="2026-11-06T10:00:00+00:00"):
        self.rows = {r["id"]: dict(r) for r in rows}
        self.changed = changed
        self.calls = []
        self.recent = []                                  # ids changed after the cached version

    def __call__(self, fn, args, timeout=30):
        self.calls.append(fn)
        req = httpx.Request("POST", "https://db.example/" + fn)
        if fn == "store_version":
            body = {"deals": {"count": len(self.rows), "changed": self.changed}, "events": {"count": 0, "changed": None}}
        elif fn == "list_deals_page":
            body = {"max_id": max(self.rows), "rows": list(self.rows.values())}
        elif fn == "list_changed_rows":
            body = {"rows": [self.rows[i] for i in self.recent if i in self.rows], "limit": args["p_limit"]}
        else:
            raise AssertionError(fn)
        return httpx.Response(200, json=body, request=req)


def _setup(monkeypatch, store):
    monkeypatch.setattr(hm, "_configured", lambda: True)
    monkeypatch.setattr(hm, "_rpc_sync", store)
    monkeypatch.setattr(hm, "_cache", {})
    monkeypatch.setattr(hm, "_versions", {})
    monkeypatch.setattr(hm, "_full_loaded_at", {})


def _expire():
    for k, (t, rows) in list(hm._cache.items()):
        hm._cache[k] = (t - hm._TTL - 1, rows)


ROWS = [{"id": "d1", "announced": "2026-11-01", "title": "A"}, {"id": "d2", "announced": "2026-11-02", "title": "B"}]


def test_nothing_changed_means_no_download(monkeypatch):
    store = FakeStore(ROWS)
    _setup(monkeypatch, store)
    assert len(hm._load("deals")) == 2
    store.calls.clear()
    _expire()
    assert len(hm._load("deals")) == 2 and store.calls == ["store_version"]


def test_only_changed_rows_are_downloaded_and_merged(monkeypatch):
    store = FakeStore(ROWS)
    _setup(monkeypatch, store)
    hm._load("deals")
    store.rows["d2"] = {"id": "d2", "announced": "2026-11-02", "title": "B (corrected)"}
    store.rows["d3"] = {"id": "d3", "announced": "2026-11-05", "title": "C"}
    store.recent, store.changed = ["d2", "d3"], "2026-11-06T15:00:00+00:00"
    store.calls.clear()
    _expire()
    rows = hm._load("deals")
    assert store.calls == ["store_version", "list_changed_rows"]
    assert [r["id"] for r in rows] == ["d3", "d2", "d1"] and rows[1]["title"] == "B (corrected)"


def test_a_removed_row_forces_a_full_reload(monkeypatch):
    store = FakeStore(ROWS + [{"id": "d3", "announced": "2026-11-03"}])
    _setup(monkeypatch, store)
    hm._load("deals")
    del store.rows["d3"]
    store.changed = "2026-11-06T15:00:00+00:00"
    store.calls.clear()
    _expire()
    rows = hm._load("deals")
    assert "list_deals_page" in store.calls and {r["id"] for r in rows} == {"d1", "d2"}


def test_a_daily_full_reload_happens_regardless(monkeypatch):
    store = FakeStore(ROWS)
    _setup(monkeypatch, store)
    hm._load("deals")
    hm._full_loaded_at["deals"] = time.monotonic() - hm._FULL_RELOAD_AFTER - 1
    store.calls.clear()
    _expire()
    hm._load("deals")
    assert "list_deals_page" in store.calls
