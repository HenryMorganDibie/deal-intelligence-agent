"""Polls (checks, average) and CSV exports."""
from datetime import date

import pytest
from fastapi import HTTPException

from src import election_export, election_polls


def poll(pollster, end, sample, shares):
    from datetime import timedelta
    start = str(date.fromisoformat(end) - timedelta(days=5))
    return election_polls.check({"pollster": pollster, "fieldwork_start": start, "fieldwork_end": end, "sample": sample,
                                 "shares": shares, "source": "https://example.org/poll"}, "ng-2027")


def test_a_poll_is_checked_and_names_resolved():
    p = poll("NOI Polls", "2026-10-20", 1200, {"Tinubu": 38, "ADC": 30, "Obi": 24})
    assert p["shares"] == {"Bola Tinubu": 38.0, "Atiku Abubakar": 30.0, "Peter Obi": 24.0} and len(p["id"]) == 16
    for bad, msg in (({"Tinubu": 60, "Obi": 50}, "more than 100"), ({"Tinubu": 40}, "at least two"),
                     ({"Tinubu": 40, "Nobody": 3}, "Unknown candidate")):
        with pytest.raises(HTTPException, match=msg):
            poll("X", "2026-10-20", 1000, bad)
    with pytest.raises(HTTPException, match="respondents"):
        poll("X", "2026-10-20", 50, {"Tinubu": 40, "Obi": 30})


def test_average_takes_each_pollsters_latest_recent_poll_weighted_by_sample():
    polls = [poll("A", "2026-09-01", 1000, {"Tinubu": 50, "Obi": 30}),
             poll("A", "2026-10-15", 1000, {"Tinubu": 40, "Obi": 40}),           # A's latest replaces the earlier one
             poll("B", "2026-10-20", 4000, {"Tinubu": 30, "Obi": 50}),
             poll("C", "2026-05-01", 9000, {"Tinubu": 90, "Obi": 5})]            # outside the 90 days
    avg = election_polls.average(polls, today=date(2026, 11, 13))
    assert avg["polls_used"] == 2 and avg["pollsters"] == ["A", "B"]
    # weights sqrt(1000) and sqrt(4000): Tinubu (40*31.62 + 30*63.25) / 94.87 = 33.3
    assert {s["candidate"]: s["share"] for s in avg["shares"]} == {"Peter Obi": 46.7, "Bola Tinubu": 33.3}


def test_csv_exports_history_and_candidates():
    name, text = election_export.export("history")
    lines = text.splitlines()
    assert name.endswith(".csv") and lines[0] == "year,state,APC,PDP,LP,NNPP,others,total_valid" and len(lines) == 1 + 3 * 37
    _, cand = election_export.export("candidates", office="governorship", state="Lagos")
    assert cand.splitlines()[0].startswith("office,state,constituency,party,name") and "Hamzat Kadri Obafemi" in cand
    with pytest.raises(ValueError):
        election_export.export("everything")
