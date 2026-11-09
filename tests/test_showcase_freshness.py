from src.engines import showcase


def _run(company, created, signals, alpha):
    return {"company": company, "created_at": created, "signal_count": signals, "top_alpha": alpha,
            "severity": "critical" if (alpha or 0) > 85 else "low", "signals": []}


def test_old_strong_run_does_not_outrank_the_latest_day():
    runs = [
        _run("Intel", "2026-11-09T16:55:00+00:00", 3, 70.0),
        _run("Equity Group", "2026-11-09T16:56:00+00:00", 0, None),
        _run("Boeing", "2026-11-06T13:00:00+00:00", 5, 90.0),
    ]
    fresh = showcase.freshest(runs)
    assert [r["company"] for r in fresh] == ["Intel", "Equity Group"]
    assert showcase.pick(fresh)["company"] == "Intel"


def test_falls_back_to_all_runs_when_the_latest_day_has_no_findings():
    runs = [
        _run("Equity Group", "2026-11-09T16:56:00+00:00", 0, None),
        _run("Boeing", "2026-11-07T13:00:00+00:00", 5, 90.0),
    ]
    assert showcase.pick(showcase.freshest(runs))["company"] == "Boeing"


def test_unparseable_dates_leave_the_list_unchanged():
    runs = [{"company": "X", "created_at": None, "signal_count": 1}]
    assert showcase.freshest(runs) == runs
