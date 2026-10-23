from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import src.hosted_market as hm


def _response(rows: list[dict], status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = "database error" if status_code != 200 else ""
    response.json.return_value = rows
    return response


def test_load_uses_bounded_pages_and_returns_complete_history(monkeypatch):
    hm._cache.clear()
    monkeypatch.setattr(hm, "_configured", lambda: True)
    calls: list[tuple[str, dict]] = []
    first_page = [{"id": str(i)} for i in range(hm._RPC_PAGE_SIZE)]
    final_page = [{"id": "last"}]

    def rpc(function: str, args: dict, timeout: float = 30):
        calls.append((function, args))
        return _response(first_page if args["p_offset"] == 0 else final_page)

    monkeypatch.setattr(hm, "_rpc_sync", rpc)
    rows = hm._load("deals")

    assert len(rows) == hm._RPC_PAGE_SIZE + 1
    assert rows[-1] == {"id": "last"}
    assert [call[0] for call in calls] == ["list_deals_page", "list_deals_page"]
    assert [call[1]["p_offset"] for call in calls] == [0, hm._RPC_PAGE_SIZE]
    assert all(call[1]["p_limit"] == hm._RPC_PAGE_SIZE for call in calls)
    assert hm._cache["deals"][1] == rows
    hm._cache.clear()


def test_load_does_not_cache_partial_history_when_later_page_fails(monkeypatch):
    hm._cache.clear()
    monkeypatch.setattr(hm, "_configured", lambda: True)
    call_count = 0

    def rpc(function: str, args: dict, timeout: float = 30):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _response([{"id": str(i)} for i in range(hm._RPC_PAGE_SIZE)])
        return _response([], status_code=500)

    monkeypatch.setattr(hm, "_rpc_sync", rpc)
    with pytest.raises(HTTPException) as exc:
        hm._load("events")

    assert exc.value.status_code == 503
    assert "events" not in hm._cache
    hm._cache.clear()


def test_load_accepts_empty_history_page(monkeypatch):
    hm._cache.clear()
    monkeypatch.setattr(hm, "_configured", lambda: True)
    calls = []

    def rpc(function: str, args: dict, timeout: float = 30):
        calls.append((function, args))
        return _response([])

    monkeypatch.setattr(hm, "_rpc_sync", rpc)
    assert hm._load("events") == []
    assert len(calls) == 1
    assert calls[0][0] == "list_events_page"
    hm._cache.clear()
