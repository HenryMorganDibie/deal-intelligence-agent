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
