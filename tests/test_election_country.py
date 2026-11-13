"""Elections beyond Nigeria: relevance, tagging, merging and events from each country's profile. Headlines are
real ones from the countries' Google News feeds (November 2026)."""
from datetime import date

from src import election_alerts, election_feed
from src.data.election_profiles import PROFILES
from src.engines import election_country as ec
from src.engines import election_news as en

TODAY = date(2026, 11, 13)


def _feed(items: list[tuple[str, str, str]]) -> str:
    """A Google News style feed: (title, publisher, day)."""
    rows = "".join(
        f"<item><title>{t} - {p}</title><link>https://news.google.com/rss/articles/{abs(hash(t + p))}</link>"
        f"<pubDate>{date.fromisoformat(d).strftime('%a, %d %b %Y')} 08:00:00 GMT</pubDate>"
        f"<description>{t}</description><source url=\"https://example.com\">{p}</source></item>"
        for t, p, d in items)
    return f"<rss><channel>{rows}</channel></rss>"


def test_every_profile_is_complete_and_dated():
    for key, p in PROFILES.items():
        assert {"country", "iso", "label", "dates", "body", "region_word", "regions", "parties", "query"} <= set(p), key
        assert all(date.fromisoformat(d) for d, _ in p["dates"])
        assert set(p.get("ambiguous_regions", ())) <= set(p["regions"])
        assert set(p.get("ambiguous_parties", ())) <= set(p["parties"])
        assert f"gl={p['iso']}" in ec.feed_url(key)


def test_kenya_relevance_keeps_election_coverage_and_drops_sport_and_public_campaigns():
    keep = ["Ruto, Sifuna tie in latest presidential opinion poll",
            "Manyora explains why Ruto could lose Western Kenya to Sifuna in 2027",
            "IEBC Reveals Next Step For 105 Political Parties Registered For 2027 Elections",
            "Opposition criticised over alleged plot to derail 2027 polls"]
    drop = ["NCTTCA launches road safety campaign",
            "Chepkirui caps Kenya's athletic Dakar campaign with silver as young stars finish third",
            "Kenya congratulates Doreen Bogdan-Martin on re-election as ITU Secretary-General",
            "What Ruto's 2032 declaration means for Kenya's political succession",
            "Uganda opposition rejects election results"]
    assert all(ec.relevant("ke-2027", t) for t in keep)
    assert not any(ec.relevant("ke-2027", t) for t in drop)


def test_gambia_and_south_sudan_relevance():
    assert ec.relevant("gm-2026", "IEC says Bensouda fully meets all nomination requirements")
    assert ec.relevant("gm-2026", "ChildFund urges political parties to prioritise children rights in 2026 elections")
    assert not ec.relevant("gm-2026", "Preview: Ivory Coast vs Gambia - prediction, team news, lineups")
    assert ec.relevant("ss-2026", "South Africa says South Sudan not ready for December elections")
    assert ec.relevant("ss-2026", "South Sudanese divided over December 2026 election preparedness")
    assert not ec.relevant("ss-2026", "Sudan army says election will follow the war")


def test_tagging_people_parties_regions_topics_and_races():
    t = ec.tag("ke-2027", "Ruto, Sifuna tie in latest presidential opinion poll")
    assert t["people"] == ["William Ruto", "Edwin Sifuna"] and t["races"] == ["presidential"] and "polls" in t["topics"]
    assert ec.tag("ke-2027", "ODM and UDA clash over Nakuru County seat")["parties"] == ["ODM", "UDA"]
    assert ec.tag("ke-2027", "ODM and UDA clash over Nakuru County seat")["states"] == ["Nakuru"]
    # A region that is also a town or people needs its county word; a party acronym that is a word needs its name.
    assert ec.tag("ke-2027", "Meru traders reopen market")["states"] == []
    assert ec.tag("ke-2027", "Meru County aspirants face off")["states"] == ["Meru"]
    assert ec.tag("ke-2027", "Jubilee celebrations in Nairobi")["parties"] == []
    assert ec.tag("ke-2027", "Jubilee Party picks its flagbearer")["parties"] == ["Jubilee"]
    assert ec.tag("ke-2027", "Rally at Uhuru Park draws thousands")["people"] == []
    assert "election_admin" in ec.tag("gm-2026", "Six Aspirants Withdraw as IEC Receives 12 Presidential Nominations")["topics"]
    assert ec.tag("ss-2026", "Unity State steps up election preparations")["states"] == ["Unity"]
    assert ec.tag("ss-2026", "Unity is the theme of the address")["states"] == []
    # "crisis" is a party crisis only when a party is named
    assert "party_crisis" not in ec.tag("ss-2026", "South Sudan's historic vote could trigger crisis")["topics"]
    assert "party_crisis" in ec.tag("ss-2026", "SPLM-IO crisis deepens as faction splits")["topics"]


def test_collect_credits_the_publisher_and_skips_social_posts_and_old_items():
    text = _feed([("Ruto opens door to EU election observers ahead of 2027 polls", "Capital FM Africa", "2026-11-12"),
                  ("President Ruto's Grand Entry in Kisii ahead of 2027 polls", "Facebook", "2026-11-12"),
                  ("IEBC sets nomination timetable for 2027 polls", "The Star, Kenya", "2026-11-01")])
    items = ec.collect("ke-2027", text, TODAY)
    assert [(i["outlet"], i["title"]) for i in items] == [
        ("Capital FM Africa", "Ruto opens door to EU election observers ahead of 2027 polls")]


def test_syndicated_reports_merge_into_one_story_per_election():
    title = "South Sudan's elections next month risk unraveling a fragile peace, envoys warn"
    text = _feed([(title, "AP News", "2026-11-11"), (title, "Toronto Star", "2026-11-11")])
    items = ec.collect("ss-2026", text, TODAY)
    stories, changed = en.merge([], items, ec.tagger("ss-2026"), "ss-2026")
    assert len(stories) == 1 and stories[0]["election"] == "ss-2026"
    assert stories[0]["outlets"] == ["AP News", "Toronto Star"] and stories[0]["candidates"] == []
    # Nigeria's records carry their election too
    assert en.record({"outlet": "Punch", "url": "https://x/1", "title": "INEC fixes date", "date": "2026-11-12"})["election"] == "ng-2027"


def test_events_group_one_countrys_incident_reports():
    a = {"id": "a", "election": "ke-2027", "day": "2026-11-12", "title": "Gunmen attack ODM rally in Kisumu County",
         "incident_types": ["violence"], "severity": "high"}
    b = {"id": "b", "election": "ke-2027", "day": "2026-11-12", "title": "ODM condemns Kisumu County rally attack",
         "incident_types": ["violence"], "severity": "medium"}
    en.assign_events([a, b], keys_fn=ec.headline_keys("ke-2027"))
    assert a["event_id"] == b["event_id"] == "a" and a["event_size"] == 2


def test_collection_job_handles_every_election_and_filters_by_election(monkeypatch):
    from src import hosted_market as hm
    store: dict[str, dict] = {}

    def fake_rpc(name, payload):
        class R:
            status_code = 200
        r = R()
        if name == "upsert_election_news":
            for row in payload["p_rows"]:
                store[row["id"]] = row
            r.json = lambda: len(payload["p_rows"])
        else:
            r.json = lambda: list(store.values())
        return r
    ke = _feed([("Ruto, Sifuna tie in latest presidential opinion poll", "Daily Nation", "2026-11-12")])
    gm = _feed([("IEC says Bensouda fully meets all nomination requirements", "The Point", "2026-11-12")])
    monkeypatch.setattr(hm, "_rpc_sync", fake_rpc)
    monkeypatch.setattr(hm, "_configured", lambda: True)
    monkeypatch.setattr(election_feed, "_fetch_sources", lambda: ([], [("ke-2027", "", ke), ("gm-2026", "", gm)], {}))
    monkeypatch.setattr(election_alerts, "deliver", lambda rows: {"sent": 0})
    election_feed._cache.clear()
    out = election_feed.collect_once(TODAY)
    assert out["items_by_election"] == {"ng-2027": 0, "ke-2027": 1, "gm-2026": 1} and out["written"] == 2
    election_feed._cache.clear()
    news = election_feed.search(election="ke-2027", since="2026-11-01")
    assert news["total"] == 1 and news["stories"][0]["people"] == ["William Ruto", "Edwin Sifuna"]
    gm_story = election_feed.search(election="gm-2026", since="2026-11-01")["stories"][0]
    assert gm_story["candidates"] == ["Talib Ahmed Bensouda"] and gm_story["parties"] == ["UNITE"]
    assert news["sources"] == ["Daily Nation"]
    assert election_feed.summary(30)["by_election"] == {"ke-2027": 1, "gm-2026": 1}
    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        election_feed.search(election="xx-2030")


def test_gambia_candidates_carry_the_commissions_status_and_their_party():
    t = ec.tag("gm-2026", "Barrow meets the Touray and Sima families in Brikama")
    # Touray and Sima alone are common surnames; the candidates need their full names or a campaign verb
    assert t["candidates"] == ["Adama Barrow"] and t["parties"] == ["NPP"]
    assert ec.tag("gm-2026", "Ousainou Darboe and Dr Isatou Touray hold rallies")["candidates"] == ["Ousainou Darboe", "Isatou Touray"]
    assert ec.tag("gm-2026", "Sima vows jobs for youth")["candidates"] == ["Modou Lamin Sima"]
    assert ec.tag("gm-2026", "Kebba Madi Bojang threatens demonstrations")["candidates"] == []   # rejected
    listed = {c["name"]: c["status"] for c in next(e for e in election_feed.elections() if e["key"] == "gm-2026")["candidates"]}
    assert listed["Talib Ahmed Bensouda"] == "confirmed" and listed["Papa Secka"] == "under review"


def test_publisher_feeds_drop_neighbours_politics_and_upgrade_google_links():
    feed = _feed([("NRM primaries: Museveni loyalists win in Uganda", "x", "2026-11-12"),
                  ("ODM sets date for Kisumu County primaries", "x", "2026-11-12")])
    items = ec.collect("ke-2027", feed, TODAY, outlet="Capital FM Africa")
    assert [i["title"] for i in items] == ["ODM sets date for Kisumu County primaries"]
    assert items[0]["outlet"] == "Capital FM Africa"
    # reached first through Google News, then through the publisher's feed: one report, now with the readable link
    gn = dict(items[0], url="https://news.google.com/rss/articles/abc")
    stories, _ = en.merge([], [gn], ec.tagger("ke-2027"), "ke-2027")
    stories, changed = en.merge(stories, [dict(items[0], url="https://capitalfm.africa/odm-primaries")], ec.tagger("ke-2027"), "ke-2027")
    assert len(stories[0]["reports"]) == 1 and stories[0]["url"] == "https://capitalfm.africa/odm-primaries" and changed


def test_full_articles_are_crawled_and_tagged_per_country():
    story = {"id": "s1", "election": "ss-2026", "day": "2026-11-12", "title": "NEC gives update on voter registration",
             "reports": [{"outlet": "Radio Tamazuj", "url": "https://www.radiotamazuj.org/en/news/article/nec-update",
                          "title": "NEC gives update on voter registration", "date": "2026-11-12"}],
             "candidates": [], "people": [], "parties": [], "states": [], "lgas": [], "topics": [], "races": []}
    targets = election_feed._crawl_targets([story], 150)
    assert [(t["name"], t["start_urls"]) for t in targets] == [("Radio Tamazuj", [story["reports"][0]["url"]])]
    assert targets[0]["extract"]["fields"]["body"]["selector"] == ".entry-content p"
    body = ["The National Elections Commission said registration in Jonglei State and Unity State continues.",
            "President Salva Kiir urged calm. " + "Officials spoke at length about logistics. " * 20,
            "Kiir later met SPLM officials in Juba. SPLM leaders backed the timetable."]
    page = {"url": story["reports"][0]["url"], "status_code": 200, "fields": {"body": body}}
    changed = en.apply_articles([story], [page], ec.body_tags("ss-2026"))
    assert changed == {"s1"} and story["candidates"] == ["Salva Kiir"] and "SPLM" in story["parties"]
    assert set(story["states"]) >= {"Jonglei", "Unity"} and story["reports"][0]["words"] > 100


def test_untracked_names_surface_who_the_lists_miss():
    stories = [{"title": t} for t in ("Kalonzo and Peter Kenneth meet", "Peter Kenneth eyes running mate slot",
                                      "Peter Kenneth joins Ruto camp", "Ruto in Nakuru County")]
    assert ec.untracked_names("ke-2027", stories) == [{"name": "Peter Kenneth", "stories": 3}]


def test_elections_list_and_alert_choices_cover_every_profile():
    keys = [e["key"] for e in election_feed.elections()]
    assert set(keys) == {"ng-2027", *PROFILES} and keys[0] == "gm-2026"      # soonest first
    assert set(election_alerts.ELECTIONS) == {*keys, "ng-2027-gov"}     # governorship: results alerts only
    f = election_alerts.clean_filters({"election": "ke-2027", "kind": "news", "states": ["Nakuru"], "people": ["William Ruto"]})
    story = {"id": "s", "election": "ke-2027", "states": ["Nakuru"], "people": ["William Ruto"], "title": "x"}
    assert election_alerts.matches(story, f)
    assert not election_alerts.matches(dict(story, election="ng-2027"), f)
    assert election_alerts._alert_item(dict(story, outlets=["Daily Nation"]))["facts_line"].startswith("Nakuru, Kenya")


def test_neighbours_politics_and_primary_schools_stay_out():
    assert not ec.relevant("ke-2027", "Blow to Muhoozi as Museveni's Party Rejects Presidential Bid")
    assert not ec.relevant("ke-2027", "Ruto Announces New Funding Model for Primary and Junior School")
    assert ec.relevant("ke-2027", "ODM primaries set for March")
    assert ec.relevant("gm-2026", "Barrow rival meets Tinubu in Abuja ahead of presidential poll")
    assert not en.relevant("FG releases funds for primary schools") and en.relevant("APC primaries: aspirants protest")
