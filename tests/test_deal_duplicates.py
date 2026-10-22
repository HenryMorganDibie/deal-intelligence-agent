from src.engines.deals import resolve_duplicates, same_transaction


def _deal(id, target, usd, day, deal_type="fund_raise", buyer=None):
    return {"id": id, "target": target, "amount_usd": usd, "announced": day, "deal_type": deal_type, "buyer": buyer}


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
    assert not same_transaction(base, _deal("c", "Ventures Platform", 84e6, "2026-10-15"))       # > 45 days
    assert not same_transaction(base, _deal("d", "Moniepoint", 84e6, "2026-08-26"))              # company
    assert not same_transaction(base, _deal("e", "Ventures Platform", 84e6, "2026-08-26", "acquisition"))
    assert not same_transaction(base, _deal("f", "Ventures Platform", None, "2026-08-26"))       # no amount


def test_duplicate_matcher_handles_rounded_amounts_and_partial_target_names():
    planned = _deal("a", "Optasia", 375e6, "2025-10-08", "ipo")
    completed = _deal("b", "Optasia South Africa listing", 345e6, "2025-11-05", "ipo")
    assert same_transaction(planned, completed)

    target_a = _deal("c", "Kenya Pipeline Company", 327e6, "2026-10-20", "acquisition")
    target_b = _deal("d", "Kenya Oil Pipeline Network", 327e6, "2026-10-22", "acquisition")
    assert same_transaction(target_a, target_b)


def test_duplicate_matcher_allows_nearby_exact_target_when_amount_is_undisclosed():
    a = _deal("a", "WeLight", None, "2026-06-25", "equity_funding", buyer="IFC")
    b = _deal("b", "WeLight", 27e6, "2026-07-01", "equity_funding", buyer="IFC")
    assert same_transaction(a, b)
    assert not same_transaction(a, _deal("c", "WeLight", 27e6, "2026-07-20", "equity_funding"))


def test_ipo_launch_and_listing_match_when_only_one_report_discloses_offer_size():
    launch = _deal("a", "Kasapreko", None, "2026-05-05", "ipo")
    launch["headline"] = "Kasapreko PLC launches IPO on the Ghana Stock Exchange"
    listing = _deal("b", "Kasapreko", 120e6, "2026-06-11", "equity_funding")
    listing["headline"] = "Kasapreko raised $120 million in its IPO and lists on the GSE"
    assert same_transaction(launch, listing)

    # Do not generalize IPO compatibility to ordinary fundraising reports.
    unrelated_stage = _deal("c", "Kasapreko", 120e6, "2026-06-11", "equity_funding")
    unrelated_stage["headline"] = "Kasapreko raises $120 million to expand production"
    assert not same_transaction(launch, unrelated_stage)


def test_extractor_and_matcher_cover_clear_reworded_duplicate_reports():
    from src.engines.deals import extract_deal

    cases = [
        (
            "Nedbank wins approval to take majority stake in Kenya’s NCBA",
            "Nedbank gets CBK approval to acquire 66pc stake in NCBA",
            "KE",
            "Businessday NG",
            "The Star, Kenya",
        ),
        (
            "SA HR startup Jem raises $8.4m Series A funding round to support product expansion",
            "South Africa’s HR startup Jem raises $8.4M Series A",
            "ZA",
            "Disrupt Africa",
            "Condia",
        ),
        (
            "Canal+ completes takeover of MultiChoice, becomes Africa’s pay-TV leader",
            "Canal+ Completes Acquisition of Multichoice",
            "ZA",
            "The Africa Report",
            "Business Post Nigeria",
        ),
    ]
    for index, (title_a, title_b, country, publisher_a, publisher_b) in enumerate(cases):
        a = extract_deal(title_a, published=f"2026-10-{10 + index:02d}", publisher=publisher_a, country_hint=country)
        b = extract_deal(title_b, published=f"2026-10-{12 + index:02d}", publisher=publisher_b, country_hint=country)
        assert a is not None, title_a
        assert b is not None, title_b
        assert same_transaction(a, b), (title_a, title_b, a, b)


def test_dedup_evaluation_reruns_current_matcher_and_reports_recall_separately():
    from evaluation.deals.score import dedup

    result, errors = dedup()
    assert result["pairs"] == 100
    assert "duplicate_recall" in result
    assert "missed_duplicate_rate" in result
    assert "baseline_saved_decisions" in result
    assert sum(result["confusion"].values()) == result["pairs"]
    assert all(error["set"] == "dedup_current" for error in errors)


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
    assert set(current["progress"]) == {"labels_a", "labels_b", "pair_labels_a", "pair_labels_b", "adjudicated", "adjudicated_pairs"}
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


def test_backfill_reaches_back_to_2010_and_the_product_loads_full_history(monkeypatch):
    from datetime import date
    from unittest.mock import AsyncMock, MagicMock

    from fastapi.testclient import TestClient

    import api.index as api
    import src.hosted_market as hm
    from src.engines import market_feed

    assert hm.HISTORY_START == date(2010, 1, 1)
    monkeypatch.setattr(hm, "_authorized_cron", lambda request: True)
    monkeypatch.setattr(hm, "_configured", lambda: True)
    collected = []

    async def collect_historical(since, until):
        collected.append((since, until))
        return []

    monkeypatch.setattr(market_feed, "collect_historical", collect_historical)
    monkeypatch.setattr(hm, "_load", lambda kind: [])
    ok = MagicMock(status_code=200, is_success=True)
    ok.json.return_value = []
    monkeypatch.setattr(hm, "_rpc", AsyncMock(return_value=ok))
    client = TestClient(api.app)

    assert client.get("/api/cron/ingest?month=2010-01").status_code == 200
    assert collected[-1] == (date(2010, 1, 1), date(2010, 1, 31))
    assert client.get("/api/cron/ingest?month=2009-12").status_code in (400, 422)


def test_history_gate_holds_back_untrustworthy_backfill_without_touching_trusted_records():
    from src.engines.deals import history_exclusion

    held = {
        "Microsoft to buy Skype for $8.5 billion": "no African market",
        "Cash strapped Air Zimbabwe buys Airbus planes": "asset purchase",
        "AU raises $351 million to fight famine, drought in East Africa": "grant, aid or programme",
        "Government Will Not Sell Bungalow To Jake in Ghana": "no transaction stated",
        "Meet The Millionaires And Billionaires Suddenly Buying Tons Of Land In Africa": "commentary",
    }
    for headline, why in held.items():
        assert why in (history_exclusion(headline) or ""), headline
    for headline in ("WNS acquires South African BPO firm for £10 mn", "Ecobank to acquire stake in Ghana’s TTB",
                     "AfDB, IFC, FMO Invest €66 Million in Dibamba Power Company in Cameroon",
                     "Bralirwa lists on the Rwanda stock exchange"):
        assert history_exclusion(headline) is None, headline


def test_history_gate_reads_french_investit_publisher_bars_and_personal_purchases():
    from src.engines.deals import history_exclusion

    held = {
        "Guinée: l'UFDG investit Dalein Diallo candidat à la présidentielle": "no transaction stated",
        "Centrafrique : Sangaris se déploie ; le 1er RHP investit Berbérati": "no transaction stated",
        "Zimbabwe Government Said to Seek Ban on Foreign Investment in Retail Sector": "no transaction stated",
        "Nigerian Singer Kizz Daniel Acquires Luxurious Seafront Mansion": "asset purchase",
        "Yumkella raises $ 500k to fight Ebola in Sierra Leone": "grant, aid or programme",
        "Francophonie Vs Commonwealth: How Rwanda Bagged $3 Billion When It Said ‘au revoir’": "commentary",
        "Marriott rachète Starwood et devient le N°1 mondial | Tourisme, hôtels, voyages en Tunisie": "no African market",
    }
    for headline, why in held.items():
        assert why in (history_exclusion(headline) or ""), headline
    for headline in ("Tunisie : Tuninvest investit dans Maille Club", "Madagascar: Sipromad investit 10M d'euros dans les cigarettes",
                     "South African rent-to-buy car subscription company Planet42 raises R1.8 billion in funding",
                     "Kigali Heights Sells Building for US$31.8 Million in Major Buyout",
                     "News | Qatar-Funded Investment Platform Acquires Crowne Plaza Hotel in Kenya",
                     "SSFR receives Rwf130m from Safaricom - Kenya | The New Times"):
        assert history_exclusion(headline) is None, headline


def test_history_gate_places_a_story_by_currency_party_or_african_outlet():
    from src.engines.deals import history_exclusion

    # The market is implicit in the headline but clear from the outlet, the amount or a known party.
    assert history_exclusion("Kitui Flour Mills to acquire 100% stake in Rafiki Millers", publishers=["Business Daily"]) is None
    assert history_exclusion("Universal Music acquires major stake in Mavin Global", publishers=["Techpoint Africa"]) is None
    assert history_exclusion("Clicks to buy Sorbet salons' holding company for R105m") is None
    assert history_exclusion("Access Bank Raises N442 Billion Capital through Syndicated Tier II Facility") is None
    # An African outlet is not enough when the headline points to another market, or names no deal at all.
    assert "no African market" in history_exclusion("QMS Medical acquires 51% stake in Saarathi Healthcare for Rs 45 crore",
                                                     publishers=["Business Daily"])
    assert "no African market" in history_exclusion("Mimecast Ltd Acquires Elevate Security", publishers=["Reuters"])
    assert "asset purchase" in history_exclusion("Singer Sean Tizzle Acquires New Chevrolet Camaro RS 2013",
                                                 publishers=["Modern Ghana"])
    assert "no transaction" in history_exclusion("Tottenham snap up Werner on loan", publishers=["The Namibian"])
    assert history_exclusion("Airtel Snaps Up Tigo Rwanda") is None
    assert history_exclusion("Uber rival acquires ride-hailing startup in Nigeria") is None


def test_merge_never_copies_soft_delete_markers():
    from src.engines.deals import merge

    # An incoming report never hides or re-points a stored record.
    stored = {"id": "k", "deal_type": "acquisition", "headline": "h"}
    merged = merge(stored, {"id": "k", "deal_type": "acquisition", "excluded": "x", "merged_into": "y"})
    assert "excluded" not in merged and "merged_into" not in merged


def test_review_scorer_reproduces_the_published_automated_results_and_refuses_partial_independent_sets():
    import json
    import pytest
    from evaluation.review import score as review_score

    assert review_score.wilson(0, 0)["rate"] is None
    w = review_score.wilson(96, 119)
    assert w["rate"] == round(96 / 119, 4) and w["ci95"][0] < w["rate"] < w["ci95"][1]
    published = json.loads((review_score.HERE / "2026" / "results_automated.json").read_text())
    assert review_score.score(2026, "automated") == published
    assert published["independent"] is False and "not independent" in published["label"]
    with pytest.raises(SystemExit):
        review_score.score(2026, "independent")


def test_review_labels_follow_the_guide_and_final_labels_need_agreement_or_a_ruling():
    import pytest
    from src.engines import review_labels as rl

    good = rl.clean_item({"is_transaction": True, "in_scope": True, "deal_type": "acquisition", "target": " Tonaton ",
                          "country": "gh", "currency": "usd", "amount": 85e6, "amount_kind": "deal_size", "extra": "dropped"})
    assert good["target"] == "Tonaton" and good["country"] == "GH" and good["currency"] == "USD" and "extra" not in good
    for bad in ({"deal_type": "loan"}, {"country": "Ghana"}, {"amount": -1}, {"is_transaction": "yes"},
                {"is_transaction": False}):                       # the last one lacks the required reason
        with pytest.raises(rl.LabelError):
            rl.clean_item(bad)
    assert rl.clean_item({"is_transaction": False, "scope_reason": "sovereign bond", "deal_type": "ipo"})["deal_type"] is None

    lab = lambda **kw: rl.clean_item({"is_transaction": True, "in_scope": True, "deal_type": "acquisition", "target": "X", **kw})
    rows = [{"role": "a", "kind": "item", "item_id": "r000", "label": lab(note="a"), "annotator": "Ama"},
            {"role": "b", "kind": "item", "item_id": "r000", "label": lab(target="x", confidence="low"), "annotator": "Bo"},
            {"role": "a", "kind": "item", "item_id": "r001", "label": lab(), "annotator": "Ama"},
            {"role": "b", "kind": "item", "item_id": "r001", "label": lab(deal_type="merger"), "annotator": "Bo"},
            {"role": "a", "kind": "item", "item_id": "r002", "label": lab(), "annotator": "Ama"},
            {"role": "b", "kind": "item", "item_id": "r002", "label": lab(deal_type="exit"), "annotator": "Bo"},
            {"role": "adjudicator", "kind": "item", "item_id": "r002", "label": lab(deal_type="exit"), "annotator": "Cy"}]
    files = rl.to_files(rows, ["r000", "r001", "r002", "r003"], ["p000"])
    assert [r["annotator"] for r in files["labels_a.jsonl"]] == ["Ama", "Ama", "Ama", ""]      # every id, blank if unlabelled
    final = {r["item_id"]: r for r in files["adjudicated_labels.jsonl"]}
    assert final["r000"]["resolution"] == "agreed"                   # notes, confidence and case may differ
    assert "r001" not in final                                       # disputed, not yet ruled
    assert final["r002"]["resolution"] == "adjudicated" and final["r002"]["deal_type"] == "exit"
    assert files["adjudicated_pair_labels.jsonl"] == []


def test_review_labelling_api_validates_labels_and_never_sends_the_system_decisions(monkeypatch):
    import json
    from unittest.mock import AsyncMock, MagicMock
    from fastapi.testclient import TestClient
    import api.index as api
    import src.hosted_market as hm

    monkeypatch.setattr(hm, "_configured", lambda: True)
    rpc = AsyncMock(return_value=MagicMock(is_success=True, json=lambda: {"year": 2026, "role": "a", "name": "Ama",
                                                                          "labels": [], "annotator_labels": None}))
    monkeypatch.setattr(hm, "_rpc", rpc)
    client = TestClient(api.app)
    token = "t" * 32
    session = client.post("/api/review/session", content=json.dumps({"token": token})).json()
    assert len(session["items"]) == 200 and len(session["pairs"]) == 88
    body = json.dumps(session)
    assert "stratum" not in body and "kept_apart" not in body and "\"record\"" not in body
    assert rpc.await_args.args[2]["p_token_hash"] != token                       # only a hash is sent to the store

    bad = client.post("/api/review/label", content=json.dumps({"token": token, "kind": "item", "item_id": "r000",
                                                               "label": {"deal_type": "loan"}}))
    assert bad.status_code == 422 and "deal_type" in bad.json()["detail"]
    rpc.return_value = MagicMock(is_success=True, json=lambda: True)
    ok = client.post("/api/review/label", content=json.dumps({"token": token, "kind": "pair", "item_id": "p000",
                                                              "label": {"same_transaction": False}}))
    assert ok.json()["saved"] is True
    assert client.post("/api/review/label", content=json.dumps({"token": token, "kind": "item", "item_id": "x1"})).status_code == 422
    assert client.post("/api/admin/review/annotators", content=json.dumps({"key": "wrong", "role": "a", "name": "A"})).status_code == 401
