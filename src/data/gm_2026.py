"""
The Gambia, presidential election of 5 December 2026: what the live results tracker needs.

Areas are the IEC's seven electoral areas, with the 2026 register the IEC chairman gave on 2 November 2026 (2021
register plus the 2026 supplementary register; the areas sum to the national 1,146,474). Constituencies are the 53
of the National Assembly (2022 list), assigned to areas by their districts; the counts match the IEC's (Banjul 3,
Kanifing 7, Brikama 12). The IEC announces each constituency's registered voters with its result; until then a
constituency's register is unknown and turnout is measured on the areas that have fully reported.

Votes are cast with marbles, so there are no rejected ballots: votes cast is the sum of the candidates' votes. The
winner is the candidate with the most votes (single round).
"""
from __future__ import annotations

ELECTION = "gm-2026"
POLLING_DAY = "2026-12-05"
NATIONAL_REGISTERED = 1_146_474

AREAS: dict[str, dict] = {
    "Banjul": {"region": "Banjul", "registered": 24_820,
               "constituencies": ["Banjul Central", "Banjul North", "Banjul South"]},
    "Kanifing": {"region": "Kanifing", "registered": 210_437,
                 "constituencies": ["Bakau", "Bundungka Kunda", "Jeshwang", "Latrikunda Sabiji", "Serekunda",
                                    "Serrekunda West", "Tallinding Kunjang"]},
    "Brikama": {"region": "West Coast", "registered": 437_020,
                "constituencies": ["Brikama North", "Brikama South", "Busumbala", "Foni Bintang", "Foni Bondali",
                                   "Foni Brefet", "Foni Jarrol", "Foni Kansala", "Kombo East", "Kombo South",
                                   "Old Yundum", "Sanimentereng"]},
    "Kerewan": {"region": "North Bank", "registered": 127_181,
                "constituencies": ["Central Baddibu", "Illiasa", "Jokadu", "Lower Baddibu", "Lower Niumi",
                                   "Sabach Sanjal", "Upper Niumi"]},
    "Mansakonko": {"region": "Lower River", "registered": 65_942,
                   "constituencies": ["Jarra Central", "Jarra East", "Jarra West", "Kiang Central", "Kiang East",
                                      "Kiang West"]},
    "Janjanbureh": {"region": "Central River", "registered": 140_899,
                    "constituencies": ["Janjanbureh", "Lower Fulladu West", "Lower Saloum", "Niamina Dankunku",
                                       "Niamina East", "Niamina West", "Niani", "Nianija", "Sami",
                                       "Upper Fulladu West", "Upper Saloum"]},
    "Basse": {"region": "Upper River", "registered": 140_175,
              "constituencies": ["Basse", "Jimara", "Kantora", "Sandu", "Tumana", "Wuli East", "Wuli West"]},
}

CONSTITUENCIES: dict[str, str] = {c: area for area, a in AREAS.items() for c in a["constituencies"]}
# Spellings the announcements use for the same constituency.
ALIASES = {"serrekunda": "Serekunda", "talinding kunjang": "Tallinding Kunjang",
           "tallinding": "Tallinding Kunjang", "latri kunda sabiji": "Latrikunda Sabiji", "sandu district": "Sandu",
           "illiassa": "Illiasa", "bundung kunda": "Bundungka Kunda", "sanementereng": "Sanimentereng",
           "upper fuladu west": "Upper Fulladu West", "lower fuladu west": "Lower Fulladu West",
           "niamina dankunku": "Niamina Dankunku", "kombo north": None}   # "Kombo North" was split in 2022

# 2021 presidential result, national votes of the four leading candidates (EU Election Observation Mission final
# report), shown for reference beside 2026's.
BASELINE_2021 = {"year": 2021, "votes": {"Adama Barrow": 457_519, "Ousainou Darboe": 238_252, "Mama Kandeh": 105_902,
                                          "Halifa Sallah": 32_435}}


def constituency(name: str) -> str | None:
    """The canonical constituency for a name as announced, or None."""
    key = " ".join((name or "").replace("’", "'").split()).lower()
    if key in ALIASES:
        return ALIASES[key]
    return next((c for c in CONSTITUENCIES if c.lower() == key), None)
