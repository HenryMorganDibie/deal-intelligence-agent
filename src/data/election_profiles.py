"""
Elections monitored beyond Nigeria: one profile per election, holding what collection and tagging need. Nigeria has
its own deeper engine (src/engines/election_news.py with src/data/elections_ng_2027.py: candidates, LGAs, polling
units, results). Adding a country is adding a profile here.

Dates are the electoral commissions' (checked 13 November 2026). Regions are the first-level divisions coverage
names. Party acronyms that are also ordinary words or other organisations are listed as ambiguous and tagged only
from the party's full name.

Candidates are the electoral commission's list, each with its status and the date it was checked; "people" are
other figures the coverage is about. Sources are publishers' own feeds whose robots.txt allows reading them (checked
13 November 2026); article selectors say where the story text is for the outlets whose article pages may be read.
Outlets are named as Google News names them, so a story reached both ways is one report.
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
        # IEBC opens presidential nominations in 2027; until then the coverage is about these figures.
        "candidates": [],
        "sources": [("Capital FM Africa", "https://capitalfm.africa/news/feed/"),
                    ("Kenyans.co.ke", "https://www.kenyans.co.ke/feeds/news"),
                    ("Daily Nation", "https://nation.africa/kenya/rss.xml"),
                    ("The Standard", "https://www.standardmedia.co.ke/rss/politics.php"),
                    ("People Daily", "https://peopledaily.digital/feed"),
                    ("The Kenya Times", "https://thekenyatimes.com/feed/"),
                    ("Kenya News Agency", "https://www.kenyanews.go.ke/feed/")],
        # Nation, People Daily and The Kenya Times refuse automated readers on article pages; The Standard's pages
        # carry no article text without scripts. Their headlines are used.
        "article_selectors": {"Capital FM Africa": ".post-content p", "Kenyans.co.ke": ".field--name-body p"},
        "slow_outlets": {"Capital FM Africa": 10},          # robots.txt: Crawl-delay 10
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
                    "CA": "Citizens' Alliance", "GAP": "Gambia Action Party", "UNITE": "UNITE Movement",
                    "APC": "Alliance of Progressive Citizens", "GLP": "Gambia Labour Party",
                    "NDP": "National Democratic Party", "NBP": "National Builders Party"},
        "ambiguous_parties": ["CA", "GAP", "NPP", "APC", "NDP", "NBP"],
        # IEC chairman Joseph Colley's briefing on presidential nominations, 12 November 2026 (reported by Kerr Fatou).
        "candidates": [
            {"name": "Adama Barrow", "party": "NPP", "status": "confirmed", "pattern": r"\bBarrow\b"},
            {"name": "Ousainou Darboe", "party": "UDP", "status": "confirmed", "pattern": r"\bOusain?ou\s+Darboe\b|\bANM\b"},
            {"name": "Talib Ahmed Bensouda", "party": "UNITE", "status": "confirmed", "pattern": r"\bBensouda\b"},
            {"name": "Isatou Touray", "party": None, "status": "confirmed", "pattern": r"\bIsatou\s+Touray\b|\bDr\.?\s+Touray\b"},
            {"name": "Modou Lamin Sima", "party": "APC", "status": "confirmed", "pattern": r"\bModou\s+Lamin\s+Sima\b|\bML\s+Sima\b|\bSima\b(?=['’]s|\s+(?:says|said|vows|pledges|promises|campaign|launches|unveils|tells|urges))"},
            {"name": "Ansu Sanneh", "party": "NBP", "status": "under review", "pattern": r"\bAnsu\s+Sanneh\b"},
            {"name": "Bakary K. Badjie", "party": None, "status": "under review", "pattern": r"\bBakary\s+(?:K\.?\s+)?Badjie\b"},
            {"name": "Lamin J. Darbo", "party": None, "status": "under review", "pattern": r"\bLamin\s+J\.?\s+Darbo\b"},
            {"name": "Almameh Gibba", "party": None, "status": "under review", "pattern": r"\bAlmameh\s+Gibba\b"},
            {"name": "Papa Secka", "party": None, "status": "under review", "pattern": r"\bPapa\s+Secka\b"},
            {"name": "Ebrima Tabora Manneh", "party": None, "status": "under review", "pattern": r"\bTabora\s+Manneh\b"},
            {"name": "Bakusa Dukureh", "party": "GLP", "status": "rejected", "pattern": r"\bDukureh\b"},
            {"name": "Kebba Madi Bojang", "party": "NDP", "status": "rejected", "pattern": r"\bKebba\s+(?:Madi\s+)?Bojang\b"},
        ],
        "candidates_checked": "2026-11-12",
        "people": {"Essa Faal": r"\bFaal\b", "Mama Kandeh": r"\bKandeh\b"},
        "sources": [("Kerr Fatou", "https://www.kerrfatou.com/feed/"), ("The Alkamba Times", "https://alkambatimes.com/feed/")],
        "article_selectors": {"Kerr Fatou": ".entry-content p", "The Alkamba Times": ".td-post-content p"},
        "slow_outlets": {"Kerr Fatou": 10},                  # robots.txt: Crawl-delay 10
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
        # The NEC has not published nominations; the SPLM has endorsed Kiir.
        "candidates": [{"name": "Salva Kiir", "party": "SPLM", "status": "endorsed by party", "pattern": r"\bKiir\b"}],
        "candidates_checked": "2026-11-13",
        "people": {"Riek Machar": r"\bMachar\b"},
        "sources": [("Radio Tamazuj", "https://www.radiotamazuj.org/en/feed"), ("Sudans Post", "https://www.sudanspost.com/feed/"),
                    ("Eye Radio", "https://eyeradio.org/feed/")],
        "article_selectors": {"Radio Tamazuj": ".entry-content p", "Sudans Post": ".entry-content p", "Eye Radio": "article p"},
        "query": '"South Sudan" (election OR elections OR polls OR campaign OR voters OR "National Elections Commission")',
    },
}
