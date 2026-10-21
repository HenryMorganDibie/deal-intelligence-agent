from src.engines.deals import resolve_duplicates, same_transaction


def _deal(id, target, usd, day, deal_type="fund_raise"):
    return {"id": id, "target": target, "amount_usd": usd, "announced": day, "deal_type": deal_type}


def test_reworded_fund_close_across_month_and_type_is_one_transaction():
    stored = _deal("a", "Ventures Platform's Pan-African Fund II", 84e6, "2026-08-26")
    for other in (
        _deal("b", "VC Firm Ventures Platform", 84e6, "2026-08-27"),
        _deal("c", "Ventures Platform", 84e6, "2026-09-09", "equity_funding"),
        _deal("d", "Ventures Platform Africa fund", 84e6, "2026-09-02"),
    ):
        assert same_transaction(stored, other), other["target"]


def test_distinct_transactions_stay_separate():
    base = _deal("a", "Ventures Platform", 84e6, "2026-08-26")
    assert not same_transaction(base, _deal("b", "Ventures Platform", 64e6, "2026-08-26"))       # amount
    assert not same_transaction(base, _deal("c", "Ventures Platform", 84e6, "2026-10-15"))       # > 30 days
    assert not same_transaction(base, _deal("d", "Moniepoint", 84e6, "2026-08-26"))              # company
    assert not same_transaction(base, _deal("e", "Ventures Platform", 84e6, "2026-08-26", "acquisition"))
    assert not same_transaction(base, _deal("f", "Ventures Platform", None, "2026-08-26"))       # no amount


def test_resolve_duplicates_rekeys_onto_stored_and_earlier_reports():
    stored = {"a": _deal("a", "Ventures Platform", 84e6, "2026-08-26")}
    new = [
        _deal("b", "VC Firm Ventures Platform", 84e6, "2026-08-27"),
        _deal("c", "Kofa", 8.1e6, "2025-04-30", "equity_funding"),
        _deal("d", "Ghana's Kofa", 8.1e6, "2025-05-01", "equity_funding"),
    ]
    assert [d["id"] for d in resolve_duplicates(new, stored)] == ["a", "c", "c"]
    assert new[0]["id"] == "b"                    # inputs are not mutated


def test_merged_and_excluded_records_are_hidden_and_new_reports_follow_the_merge():
    from src.engines.deals import canonical_id, is_visible

    stored = {
        "keep": _deal("keep", "Ventures Platform", 84e6, "2026-08-26"),
        "dup": {**_deal("dup", "VC Firm Ventures Platform", 84e6, "2026-08-27"), "merged_into": "keep"},
        "gone": {**_deal("gone", "World Bank Group", 200e9, "2026-01-01"), "excluded": "programme"},
    }
    assert [i for i, d in stored.items() if is_visible(d)] == ["keep"]
    assert canonical_id("dup", stored) == "keep" and canonical_id("new", stored) == "new"
    again = resolve_duplicates([_deal("dup", "VC Firm Ventures Platform", 84e6, "2026-08-27")], stored)
    assert again[0]["id"] == "keep"
    # A hidden record is never the match for a different report.
    fresh = resolve_duplicates([_deal("x", "World Bank Group", 200e9, "2026-01-02")], stored)
    assert fresh[0]["id"] == "x"


def test_excluded_events_are_hidden():
    from src.hosted_market import _visible_events

    rows = [{"id": "a"}, {"id": "b", "excluded": "no African party"}]
    assert [e["id"] for e in _visible_events(rows)] == ["a"]


def test_independent_review_reports_the_latest_year_and_serves_its_files():
    import json as _json

    from src.hosted_market import _REVIEW, _download_body, _independent_review, _review_years

    assert 2026 in _review_years()
    review = _independent_review()
    current = review["current"]
    assert current["year"] == max(_review_years())
    manifest = _json.loads((_REVIEW / str(current["year"]) / "manifest.json").read_text())
    assert current["items"] == manifest["items"]
    assert current["status"] == "awaiting independent labels"
    assert set(current["progress"]) == {"labels_a", "labels_b", "pair_labels_a", "pair_labels_b", "adjudicated"}
    assert "guidelines_md" not in current
    for name in current["downloads"]:
        assert _download_body(name), name
    # Older names keep working, and annotators get inputs only.
    assert _download_body("review_2026_items.jsonl")
    item = _json.loads((_REVIEW / "2026" / "items.jsonl").read_text().splitlines()[0])
    assert set(item) == {"item_id", "title", "publisher", "date"}


def test_review_guide_is_served_from_the_manifest_when_markdown_is_not_bundled(monkeypatch):
    import src.hosted_market as hm

    real = hm._review_downloads
    monkeypatch.setattr(hm, "_review_downloads", lambda: {
        **real(), "review_2026_guidelines.md": ("evaluation/review/MISSING.md", "text/markdown")})
    body = hm._download_body("review_2026_guidelines.md")
    assert body and body.startswith("# ")


def test_a_new_year_appears_without_code_changes(tmp_path, monkeypatch):
    import json as _json

    import src.hosted_market as hm

    for year, items in ((2026, 200), (2027, 180)):
        folder = tmp_path / str(year)
        folder.mkdir()
        (folder / "manifest.json").write_text(_json.dumps({"items": items, "pairs": 90, "strata": {}, "pair_strata": {}}))
    monkeypatch.setattr(hm, "_REVIEW", tmp_path)
    review = hm._independent_review()
    assert review["current"]["year"] == 2027 and review["current"]["items"] == 180
    assert [r["year"] for r in review["previous"]] == [2026]
    assert "review_2027_items.jsonl" in hm._review_downloads()


def test_review_builder_never_redraws_an_existing_year(capsys):
    from evaluation.review.build import main

    main(["--year", "2026"])
    assert "never redrawn" in capsys.readouterr().out
