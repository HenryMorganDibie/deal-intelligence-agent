from src.engines.market_feed import names_only_foreign_countries, to_events


def test_foreign_story_from_a_country_search_gets_no_country():
    """Live regression: a Paraguayan bank collapse came back from a French-language Senegal query."""
    title = "Le président du Paraguay Santiago Peña annonce sa démission après l’effondrement d’Ueno Bank"
    assert names_only_foreign_countries(title)
    events = to_events([{"title": title, "snippet": "", "country_hint": "SN", "date": "2026-11-05"}])
    assert all(e["country"] is None for e in events)


def test_story_naming_no_country_still_takes_the_search_country():
    events = to_events([{"title": "Dangote Cement acquires majority stake in rival cement maker", "snippet": "",
                         "country_hint": "NG", "date": "2026-11-05"}])
    assert events and events[0]["country"] == "NG"


def test_african_country_named_alongside_a_foreign_one_is_kept():
    assert not names_only_foreign_countries("Sonatel lance une offre en France et au Sénégal")
    assert not names_only_foreign_countries("MTN Nigeria signs deal with US firm")
    assert names_only_foreign_countries("Banco do Brasil acquires stake")


def test_africa_or_a_hyphenated_african_country_counts_as_african():
    assert not names_only_foreign_countries("Zambia-Saudi Arabia debt restructuring agreement a show of confidence")
    assert not names_only_foreign_countries("China's $4 billion bid for African gold assets collapses")
    assert names_only_foreign_countries("bp Sells Stake in Norway's Aker for Over $1Bn")
