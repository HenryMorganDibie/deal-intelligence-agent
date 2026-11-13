from datetime import date

import pytest

from src.engines import election_news as en

FEED = """<rss><channel>
<item><title>2027: INEC begins distribution of non-sensitive election materials</title>
<link>https://punch.example/inec-materials</link><pubDate>Thu, 12 Nov 2026 08:00:00 +0000</pubDate>
<description>ABUJA — The Independent National Electoral Commission has begun...</description></item>
<item><title>Arsenal hold Barcelona to 1-1 draw</title><link>https://punch.example/arsenal</link>
<pubDate>Thu, 12 Nov 2026 09:00:00 +0000</pubDate></item>
<item><title>Lagos APC condemns attack on NDC members, denies involvement</title>
<link>https://punch.example/lagos-apc</link><pubDate>Wed, 11 Nov 2026 10:00:00 +0000</pubDate></item>
<item><title>Old story about 2023</title><link>https://punch.example/old</link>
<pubDate>Mon, 02 Nov 2026 10:00:00 +0000</pubDate></item>
</channel></rss>"""
FEED2 = """<rss><channel>
<item><title>2027: INEC begins deploying non-sensitive materials</title>
<link>https://vanguard.example/inec-deploys</link><pubDate>Thu, 12 Nov 2026 11:00:00 +0000</pubDate></item>
</channel></rss>"""
TODAY = date(2026, 11, 12)


def test_tags_candidates_parties_states_topics_and_races():
    t = en.tag("2027: Atiku can't unite Adamawa, let alone Nigeria — Shettima")
    assert t["candidates"] == ["Kashim Shettima", "Atiku Abubakar"] and t["parties"] == ["ADC", "APC"]
    assert t["states"] == ["Adamawa"]
    t = en.tag("Thugs attack Pantami's campaign rally in Gombe", "")
    assert t["topics"][:2] == ["campaign", "security"] and t["states"] == ["Gombe"]
    assert en.tag("Kwara PDP gov candidate pledges security fund")["races"] == ["governorship"]
    assert en.tag("Jaji Wins APC Re-run Primary in Zamfara")["topics"] == ["results"]


def test_relatives_namesakes_and_ambiguous_words_are_not_candidates_or_places():
    assert en.tag("2027 AND THE OLUREMI TINUBU FACTOR")["candidates"] == []
    assert en.tag("Obi Cubana hosts friends in Lagos")["candidates"] == []
    assert en.tag("Peter Obi visits Yelwata")["candidates"] == ["Peter Obi"]
    assert en.tag("Niger Delta youths protest")["states"] == []
    assert en.tag("Gains and Wins of President Tinubu's Akwa Ibom Visit")["topics"] == []
    assert en.tag("BP posts record profit")["parties"] == []          # an oil company, not the Boot Party
    assert en.tag("Spanish group trains journalists", "ABUJA — Reporters from Edo and Lagos")["states"] == ["Edo", "Lagos"]


def test_relevance_keeps_election_coverage_and_drops_the_rest():
    assert en.relevant("Lagos APC condemns attack on NDC members, denies involvement")
    assert en.relevant("1.37M Nigerians Pre-Register in One Week As In-Person Registration Begins")
    assert en.relevant("APC and The Ides of January 2027")
    assert not en.relevant("Arsenal hold Barcelona to 1-1 draw in women's Champions League")
    assert not en.relevant("2027 budget: Senate passes N54trn appropriation bill")
    assert not en.relevant("Delta targets 5,000 jobs from glass factory revival")


def test_two_outlets_reporting_one_story_become_one_record_with_both_reports():
    items = en.collect([("Punch", FEED), ("Vanguard", FEED2)], TODAY)
    assert {i["url"] for i in items} == {"https://punch.example/inec-materials", "https://punch.example/lagos-apc",
                                         "https://vanguard.example/inec-deploys"}     # sport and old news left out
    stories, changed = en.merge([], items)
    assert len(stories) == 2 and changed == {s["id"] for s in stories}
    inec = next(s for s in stories if "INEC" in s["title"])
    assert inec["outlets"] == ["Punch", "Vanguard"] and len(inec["reports"]) == 2
    # The same items again change nothing; a stored story picks up a new outlet's report.
    again, changed = en.merge([dict(s, reports=list(s["reports"])) for s in stories], items)
    assert changed == set() and len(again) == 2
    s = en.summary(stories)
    assert s["stories"] == 2 and s["reports"] == 3
    assert {"name": "APC", "stories": 1, "reports": 1} in s["parties"]


def test_collection_job_writes_only_changed_stories_and_the_api_serves_them(monkeypatch):
    from fastapi.testclient import TestClient
    import api.index as api
    from src import election_feed, hosted_market as hm, public_api

    stored, writes = [], []

    class R:
        status_code = 200

        def __init__(self, p):
            self._p = p
            self.text = ""

        def json(self):
            return self._p

    def fake_rpc(fn, args, timeout=30):
        if fn == "list_election_news":
            return R([s for s in stored if s["day"] >= args["p_since"]])
        if fn == "upsert_election_news":
            writes.append(len(args["p_rows"]))
            for row in args["p_rows"]:
                stored[:] = [s for s in stored if s["id"] != row["id"]] + [row]
            return R(len(args["p_rows"]))
        raise AssertionError(fn)

    monkeypatch.setattr(hm, "_rpc_sync", fake_rpc)
    monkeypatch.setattr(hm, "_configured", lambda: True)
    monkeypatch.setattr(election_feed, "_fetch_sources", lambda: ([("Punch", FEED), ("Vanguard", FEED2)], {"Punch": "200"}))
    election_feed._cache.clear()
    out = election_feed.collect_once(TODAY)
    assert out["stories_changed"] == 2 and out["written"] == 2
    assert election_feed.collect_once(TODAY)["stories_changed"] == 0          # a repeat run writes nothing

    async def ok(request, response, count=True):
        return {"plan": "pro"}
    monkeypatch.setattr(public_api, "authorize", ok)
    client = TestClient(api.app)
    r = client.get("/v1/elections/news", params={"party": "NDC", "since": "2026-11-01"})
    assert r.status_code == 200 and r.json()["total"] == 1 and r.json()["stories"][0]["parties"] == ["APC", "NDC"]
    r = client.get("/v1/elections/news", params={"topic": "inec_logistics", "since": "2026-11-01"})
    assert r.json()["stories"][0]["outlets"] == ["Punch", "Vanguard"]
    assert client.get("/v1/elections/news", params={"since": "soon"}).status_code == 400
    assert "elections/news" in " ".join(client.get("/v1").json()["endpoints"])


@pytest.mark.parametrize("acr", ["APC", "ADC", "NDC", "PDP", "SDP", "PRP", "YPP", "ZLP", "AAC", "APM", "ADP", "NDP"])
def test_every_distinct_party_acronym_is_recognised(acr):
    assert acr in en.tag(f"{acr} unveils campaign council")["parties"]


def test_sitting_president_alone_needs_election_wording():
    assert not en.relevant("Tinubu skips COP31 summit for third consecutive year")
    assert not en.relevant("Senate Committee Warns NMDPRA Nominees Against Frustrating Tinubu's Reforms")
    assert en.relevant("2027: Tinubu has no competitor in South-South — Akpabio")
    assert en.relevant("Tinubu building political power, not national unity – Makinde")   # a challenger named


def test_outlets_that_refuse_crawlers_are_read_from_google_news_and_counted_once():
    sources = dict((o, u) for o, u in en.all_sources() if "news.google.com" in u)
    assert set(sources) == {"TheCable", "Guardian", "Channels"}
    assert "site:thecable.ng" in sources["TheCable"]
    items = [{"outlet": "TheCable", "url": "https://news.google.com/a", "date": "2026-11-12",
              "title": "Shettima asks Ondo voters to deliver 1.2m votes for Tinubu in 2027"},
             {"outlet": "TheCable", "url": "https://news.google.com/b", "date": "2026-11-12",
              "title": "Shettima asks Ondo residents to deliver 1.2m votes for Tinubu in 2027"},
             {"outlet": "Vanguard", "url": "https://vanguard.example/c", "date": "2026-11-12",
              "title": "Shettima asks Ondo voters to deliver 1.2m votes for Tinubu"}]
    stories, _ = en.merge([], items)
    assert len(stories) == 1 and [r["outlet"] for r in stories[0]["reports"]] == ["TheCable", "Vanguard"]


def _story():
    return en.record({"outlet": "Punch", "date": "2026-11-12", "snippet": "",
                      "url": "https://punchng.com/matawalle-tinubu/?utm_source=rss.punchng.com&utm_medium=web",
                      "title": "My Ambition Is To Ensure Tinubu's 2027 Victory, Says Matawalle"})


def test_crawl_targets_cover_unread_articles_of_crawlable_outlets_only():
    a = _story()
    g = en.record({"outlet": "TheCable", "url": "https://news.google.com/rss/articles/x", "date": "2026-11-12",
                   "title": "Atiku visits Kano ahead of 2027", "snippet": ""})
    targets = en.crawl_targets([a, g])
    assert [t["name"] for t in targets] == ["Punch"] and targets[0]["max_depth"] == 0
    assert targets[0]["extract"]["fields"]["body"] == {"selector": ".post-content p", "all": True}
    a["reports"][0]["words"] = 0                          # read (or unreadable) once: not crawled again
    assert en.crawl_targets([a, g]) == []


def test_full_article_adds_what_the_story_is_about_not_every_passing_mention():
    s = _story()
    lede = "Former Zamfara governor Bello Matawalle said at a campaign rally in Gusau that the APC will deliver Zamfara for Tinubu. "
    rest = ("x " * 400) + "He also mentioned Kano once. The campaign in Zamfara continues."
    page = {"url": "https://punchng.com/matawalle-tinubu", "status_code": 200,
            "fields": {"body": [lede, rest, "Subscribe to our digital E-Editions here."]}}
    changed = en.apply_articles([s], [page])                # matched despite the tracking parameters
    assert changed == {s["id"]} and s["reports"][0]["words"] > 400
    assert "Zamfara" in s["states"] and "Kano" not in s["states"]           # once, outside the lede: left out
    assert "campaign" in s["topics"] and s["full_text_reports"] == 1
    assert en.article_text(["November 12, 2026", "Real text.", "Subscribe to our digital E-Editions"]) == "Real text."


def test_unreadable_page_is_marked_so_it_is_not_retried_and_tags_stay():
    s = _story()
    tags = {k: list(s[k]) for k in ("candidates", "parties", "states", "topics", "races")}
    en.apply_articles([s], [{"url": s["url"], "status_code": 403, "fields": {}}])
    assert s["reports"][0]["words"] == 0 and {k: s[k] for k in tags} == tags


@pytest.mark.parametrize("title,types,severity", [
    ("Gunmen kill INEC official in Imo, set office ablaze", ["violence", "arson"], "high"),
    ("Hoodlums torch INEC office in Enugu", ["thuggery", "arson"], "high"),
    ("Police fire shots as thugs disrupt NDC Hall meeting in Lagos", ["thuggery"], "high"),
    ("Thugs snatch ballot boxes in Rivers polling unit", ["thuggery", "ballot_snatching"], "medium"),
    ("BVAS malfunction delays accreditation in Kano polling units", ["technology_failure"], "low"),
    ("Vote buying: EFCC arrests three agents in Ekiti", ["vote_buying", "arrest"], "low"),
    ("Late arrival of materials stalls voting in Anambra", ["logistics"], "low"),
])
def test_incidents_are_typed_and_rated_from_the_headline(title, types, severity):
    assert en.incidents(title) == {"incident_types": types, "severity": severity}


def test_words_of_war_and_background_are_not_incidents():
    assert en.incidents("ADC, APM attack APC over alleged 'repackaged old promises in new manifesto'") == {}
    assert en.incidents("Finally, Obi visits Yelwata, honours 271 victims", "Over 200 people were killed in June") == {}
    assert en.incidents("Tinubu kills it with speech") == {}
    assert en.incidents("TheCable journalist attacked at NDC town hall")["incident_types"] == ["violence"]


def test_lgas_are_tagged_only_within_a_named_state():
    assert en.tag("Katsina APC condemns Funtua violence")["lgas"] == ["Funtua, Katsina"]
    assert en.tag("Thugs attack NDC members in Ikeja, Lagos")["lgas"] == ["Ikeja, Lagos"]
    assert en.tag("Funtua youths protest")["lgas"] == []                  # no state named: not placed
    assert en.tag("Peter Obi visits Nasarawa")["lgas"] == []              # Obi is also an LGA in Nasarawa


def test_old_stories_get_new_tags_once_and_the_incident_feed_filters(monkeypatch):
    from src import election_feed
    old = {"id": "a", "day": "2026-11-12", "title": "Police fire shots as thugs disrupt NDC meeting in Ikeja, Lagos",
           "snippet": "", "candidates": [], "parties": ["NDC"], "states": ["Lagos"], "topics": [], "races": [],
           "reports": [{"outlet": "Punch", "url": "https://p.example/a", "title": "x", "date": "2026-11-12"}]}
    calm = dict(old, id="b", title="APC unveils campaign council in Kano", states=["Kano"], parties=["APC"])
    stories = [dict(old), dict(calm)]
    assert en.retag_missing(stories) == {"a", "b"} and en.retag_missing(stories) == set()
    assert stories[0]["severity"] == "high" and stories[0]["lgas"] == ["Ikeja, Lagos"]
    monkeypatch.setattr(election_feed, "_load", lambda since: stories)
    feed = election_feed.incident_feed(state="Lagos", severity="medium", since="2026-11-01")
    assert feed["total"] == 1 and feed["by_severity"]["high"] == 1 and feed["by_type"] == {"thuggery": 1}
    assert election_feed.incident_feed(lga="Ikeja", since="2026-11-01")["total"] == 1
    assert election_feed.search(lga="ikeja", since="2026-11-01")["total"] == 1
    with pytest.raises(Exception):
        election_feed.incident_feed(severity="extreme")


def test_one_incident_covered_from_many_angles_is_one_event():
    s = [{"id": "a", "day": "2026-11-12", "title": "Thugs attack NDC supporters in Lagos", "incident_types": ["violence", "thuggery"]},
         {"id": "b", "day": "2026-11-12", "title": "APC condemns attack on NDC Lagos town hall", "incident_types": ["violence"]},
         {"id": "c", "day": "2026-11-13", "title": "Obi condemns Lagos attack", "incident_types": ["violence"]},
         {"id": "d", "day": "2026-11-12", "title": "Thugs attack Pantami's campaign rally in Gombe", "incident_types": ["violence"]},
         {"id": "e", "day": "2026-11-12", "title": "EU warns of surge in violence", "incident_types": ["violence"]},
         {"id": "f", "day": "2026-11-20", "title": "Thugs attack NDC supporters in Lagos again", "incident_types": ["violence"]},
         {"id": "g", "day": "2026-11-12", "title": "APC unveils campaign council in Lagos", "incident_types": []}]
    changed = en.assign_events(s)
    ev = {x["id"]: x.get("event_id") for x in s}
    assert ev["a"] == ev["b"] == ev["c"] == "a" and s[0]["event_size"] == 3     # Obi's party links him to NDC
    assert ev["d"] == "d" and ev["e"] == "e" and ev["f"] == "f" and ev["g"] is None   # other place, no place, later
    assert "a" in changed and en.assign_events(s) == set()                        # stable on the next run
