"""
CSV exports of the election datasets, one row per record with list fields joined by "; ", for spreadsheets and
newsroom tools: news, incidents, live results, historical results and candidates.
"""
from __future__ import annotations

import csv
import io
from typing import Iterable, Optional

DATASETS = ("news", "incidents", "live", "history", "candidates")


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "; ".join(_cell(x) for x in v)
    if isinstance(v, dict):
        return "; ".join(f"{k}: {_cell(x)}" for k, x in v.items())
    return str(v)


def to_csv(rows: Iterable[dict], columns: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    for r in rows:
        w.writerow([_cell(r.get(c)) for c in columns])
    return buf.getvalue()


NEWS_COLUMNS = ["day", "election", "title", "url", "outlets", "language", "candidates", "gov_candidates",
                "senate_candidates", "people", "parties", "states", "lgas", "topics", "races", "incident_types",
                "severity", "event_id", "event_size"]


def export(dataset: str, election: Optional[str] = None, since: Optional[str] = None, state: Optional[str] = None,
           office: Optional[str] = None) -> tuple[str, str]:
    """(filename, csv text)."""
    if dataset not in DATASETS:
        raise ValueError("dataset must be one of: " + ", ".join(DATASETS) + ".")
    if dataset == "news":
        from src import election_feed
        rows = election_feed.search(election=election, since=since, state=state, limit=20000)["stories"]
        return f"election-news-{election or 'all'}.csv", to_csv(rows, NEWS_COLUMNS)
    if dataset == "incidents":
        from src import election_feed
        rows = election_feed.incident_feed(state=state, since=since, limit=20000, election=election)["incidents"]
        return f"election-incidents-{election or 'all'}.csv", to_csv(rows, NEWS_COLUMNS)
    if dataset == "live":
        from src import election_live
        t = election_live.results(election or "ng-2027")
        names = t["candidates"]
        rows = [{"unit": u["unit"], "area": u["area"], "status": u["status"], "valid": u["valid"],
                 "rejected": u["rejected"], "votes_cast": u["votes_cast"], "registered": u["registered"],
                 "turnout": u["turnout"], "winner": u["winner"], "source": u["source"],
                 **{n: next((x["votes"] for x in u["results"] if x["candidate"] == n), 0 if u["results"] else None)
                    for n in names}} for u in t["units"]]
        cols = ["unit", "area", "status", *names, "valid", "rejected", "votes_cast", "registered", "turnout",
                "winner", "source"]
        return f"live-results-{t['election']}.csv", to_csv(rows, cols)
    if dataset == "history":
        from src.data import ng_results_history as hist
        rows = []
        for year, states in hist.RESULTS.items():
            for st, r in states.items():
                rows.append({"year": year, "state": st, **{p: r.get(p) for p in ("APC", "PDP", "LP", "NNPP", "others")},
                             "total_valid": hist.state_result(year, st)["total_valid"]})
        return "nigeria-presidential-results-2015-2023.csv", to_csv(
            rows, ["year", "state", "APC", "PDP", "LP", "NNPP", "others", "total_valid"])
    from src import ng_candidates
    rows = ng_candidates.search(office=office, state=state, limit=100_000)["candidates"]
    return f"nigeria-candidates-2027{'-' + office if office else ''}.csv", to_csv(
        rows, ["office", "state", "constituency", "party", "name", "running_mate", "age", "gender", "remarks"])
