"""
Elections monitored beyond Nigeria: one profile per election, holding what collection and tagging need. Nigeria has
its own deeper engine (src/engines/election_news.py with src/data/elections_ng_2027.py: candidates, LGAs, polling
units, results). Adding a country is adding a profile here.

Dates are the electoral commissions' (checked 13 November 2026). Regions are the first-level divisions coverage
names. Party acronyms that are also ordinary words or other organisations are listed as ambiguous and tagged only
from the party's full name.
"""
from __future__ import annotations

PROFILES: dict[str, dict] = {
    "ke-2027": {
        "country": "Kenya", "iso": "KE", "label": "Kenya: 2027 general election",
        "dates": [("2027-08-10", "General election")],
        "body": ("IEBC", "Independent Electoral and Boundaries Commission"),
        "region_word": "County",
        "regions": ["Mombasa", "Kwale", "Kilifi", "Tana River", "Lamu", "Taita Taveta", "Garissa", "Wajir", "Mandera",
                    "Marsabit", "Isiolo", "Meru", "Tharaka-Nithi", "Embu", "Kitui", "Machakos", "Makueni", "Nyandarua",
                    "Nyeri", "Kirinyaga", "Murang'a", "Kiambu", "Turkana", "West Pokot", "Samburu", "Trans-Nzoia",
                    "Uasin Gishu", "Elgeyo-Marakwet", "Nandi", "Baringo", "Laikipia", "Nakuru", "Narok", "Kajiado",
                    "Kericho", "Bomet", "Kakamega", "Vihiga", "Bungoma", "Busia", "Siaya", "Kisumu", "Homa Bay",
                    "Migori", "Kisii", "Nyamira", "Nairobi"],
        "ambiguous_regions": ["Meru", "Embu", "Nandi", "Narok", "Lamu", "Isiolo"],   # also towns or peoples: need "County"
        "parties": {"UDA": "United Democratic Alliance", "ODM": "Orange Democratic Movement",
                    "Jubilee": "Jubilee Party", "Wiper": "Wiper Democratic Movement", "DCP": "Democracy for Citizens Party",
                    "ANC": "Amani National Congress", "Ford-Kenya": "Forum for the Restoration of Democracy-Kenya",
                    "KANU": "Kenya African National Union", "DAP-K": "Democratic Action Party-Kenya"},
        "ambiguous_parties": ["ANC", "Jubilee", "Wiper"],
        # Leading figures, matched by the names headlines use. A name here is someone the coverage is about, declared
        # candidate or not; patterns stop place names that share a word (Uhuru Park, Uhuru Highway).
        "people": {"William Ruto": r"\bRuto\b", "Rigathi Gachagua": r"\bGachagua\b", "Kalonzo Musyoka": r"\bKalonzo\b",
                   "Edwin Sifuna": r"\bSifuna\b", "Fred Matiang'i": r"\bMatiang['’]?i\b",
                   "Uhuru Kenyatta": r"\bKenyatta\b|\bUhuru\b(?!\s+(?:Park|Highway|Gardens|Heights|Market))",
                   "Kithure Kindiki": r"\bKindiki\b", "Martha Karua": r"\bKarua\b",
                   "Eugene Wamalwa": r"\bWamalwa\b", "George Natembeya": r"\bNatembeya\b",
                   "Okiya Omtatah": r"\bOmtatah\b"},
        "query": '"Kenya" (election OR elections OR polls OR campaign OR IEBC OR voters)',
    },
    "gm-2026": {
        "country": "The Gambia", "iso": "GM", "label": "The Gambia: presidential (2026) and parliamentary (2027)",
        "dates": [("2026-12-05", "Presidential election"), ("2027-04-10", "Parliamentary election")],
        "body": ("IEC", "Independent Electoral Commission"),
        "region_word": "Region",
        "regions": ["Banjul", "Kanifing", "West Coast", "North Bank", "Lower River", "Central River", "Upper River"],
        "ambiguous_regions": ["West Coast", "North Bank", "Lower River", "Central River", "Upper River"],
        "parties": {"UDP": "United Democratic Party", "NPP": "National People's Party",
                    "GDC": "Gambia Democratic Congress", "APRC": "Alliance for Patriotic Reorientation and Construction",
                    "PDOIS": "People's Democratic Organisation for Independence and Socialism",
                    "CA": "Citizens' Alliance", "GAP": "Gambia Action Party"},
        "ambiguous_parties": ["CA", "GAP", "NPP"],
        "people": {"Adama Barrow": r"\bBarrow\b", "Talib Ahmed Bensouda": r"\bBensouda\b", "Essa Faal": r"\bFaal\b",
                   "Mama Kandeh": r"\bKandeh\b"},
        "query": '"Gambia" (election OR elections OR polls OR campaign OR IEC OR voters)',
    },
    "ss-2026": {
        "country": "South Sudan", "iso": "SS", "label": "South Sudan: 2026 general election",
        "dates": [("2026-12-22", "General election")],
        "body": ("NEC", "National Elections Commission"),
        "region_word": "State",
        "regions": ["Central Equatoria", "Eastern Equatoria", "Western Equatoria", "Jonglei", "Unity", "Upper Nile",
                    "Lakes", "Warrap", "Northern Bahr el Ghazal", "Western Bahr el Ghazal", "Abyei", "Pibor", "Ruweng",
                    "Juba"],
        "ambiguous_regions": ["Unity", "Lakes", "Upper Nile"],
        "parties": {"SPLM": "Sudan People's Liberation Movement",
                    "SPLM-IO": "Sudan People's Liberation Movement-in-Opposition",
                    "SSOA": "South Sudan Opposition Alliance", "NDM": "National Democratic Movement"},
        "ambiguous_parties": ["NDM"],
        "people": {"Salva Kiir": r"\bKiir\b", "Riek Machar": r"\bMachar\b"},
        "query": '"South Sudan" (election OR elections OR polls OR campaign OR voters OR "National Elections Commission")',
    },
}
