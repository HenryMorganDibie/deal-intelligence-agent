"""
Nigeria's 2027 general election: the people, parties and places election coverage is tagged with.

Presidential tickets are INEC's final list of 18 (published 12 September 2026, signed by the Commission's
Secretary). Polling days follow INEC's revised timetable: presidential and National Assembly on 16 January 2027,
governorship and state assembly on 6 February 2027.

Matching is deliberately conservative. A surname alone counts only where it is distinctive in Nigerian political
coverage ("Tinubu", "Atiku", "Kwankwaso"); common or shared names need the full name ("Donald Duke", not "Duke").
Where relatives share a surname, their first names are listed so they are not tagged as the candidate.
"""
from __future__ import annotations

from datetime import date

PRESIDENTIAL_DAY = date(2027, 1, 16)
GOVERNORSHIP_DAY = date(2027, 2, 6)

# (party acronym, party name, candidate, running mate)
TICKETS: tuple[tuple[str, str, str, str], ...] = (
    ("APC", "All Progressives Congress", "Bola Tinubu", "Kashim Shettima"),
    ("ADC", "African Democratic Congress", "Atiku Abubakar", "Chibuike Rotimi Amaechi"),
    ("NDC", "Nigerian Democratic Congress", "Peter Obi", "Rabiu Musa Kwankwaso"),   # INEC: Peter Gregory Obi / Musa Mohammed Rabiu Kwankwaso
    ("LP", "Labour Party", "Sunday Chibuzo Okereke", "Hajja Bintu Konto"),
    ("PDP", "Peoples Democratic Party", "Sandy Ojang Onor", "Umaru Babangida"),
    ("AA", "Action Alliance", "Rufai Adekunle Omo-Aje", "Shehu Hussaini"),
    ("ADP", "Action Democratic Party", "Aliyu Abbas-Bin", "Chinazam Ike"),
    ("APP", "Allied Peoples Party", "Kabiru Yusuf", "Peace Egobia Ofordile"),
    ("AAC", "African Action Congress", "Omoyele Sowore", "Haruna Garba Magashi"),
    ("APM", "Allied Peoples Movement", "Seyi Makinde", "Musa Lawal Daura"),
    ("BP", "Boot Party", "Sunday Adenuga", "Usman Turaki Mustapha"),
    ("DLA", "Democratic Leadership Alliance", "Moses Olusoji Adebisi", "Nafisat Usaku Abubakar"),
    ("NDP", "National Democratic Party", "Ada Elizabeth Fredrick Okwori", "Uchenna Anthony Chukwuemeka"),
    ("NRM", "National Rescue Movement", "Nkem Esther Okereke", "Nasir Muhammed Sulaiman"),
    ("PRP", "People's Redemption Party", "Donald Duke", "Kabiru Rabiu"),
    ("SDP", "Social Democratic Party", "Adewole Adebayo", "Usman Bugaje"),
    ("YPP", "Young Progressive Party", "Peter Ada Agada", "Patience Ndidi Key"),
    ("ZLP", "Zenith Labour Party", "Daniel Nwanyanwu", "Hassan Khalid"),
)

# Extra ways a candidate is named in headlines, beyond the full name: distinctive surnames and common forms.
ALIASES: dict[str, tuple[str, ...]] = {
    "Bola Tinubu": ("Tinubu", "Asiwaju"),
    "Kashim Shettima": ("Shettima",),
    "Atiku Abubakar": ("Atiku",),
    "Chibuike Rotimi Amaechi": ("Amaechi", "Rotimi Amaechi"),
    "Peter Obi": ("Obi",),
    "Rabiu Musa Kwankwaso": ("Kwankwaso", "Musa Kwankwaso"),
    "Sandy Ojang Onor": ("Sandy Onor", "Onor"),
    "Omoyele Sowore": ("Sowore",),
    "Seyi Makinde": ("Makinde", "Oluseyi Makinde", "Oluseyi Abiodun Makinde"),
    "Rufai Adekunle Omo-Aje": ("Omo-Aje",),
    "Aliyu Abbas-Bin": ("Abbas-Bin",),
    "Ada Elizabeth Fredrick Okwori": ("Okwori",),
    "Adewole Adebayo": ("Adewole Ebenezer Adebayo",),
    "Daniel Nwanyanwu": ("Nwanyanwu", "Daniel Daberechukwu Nwanyanwu"),
    "Peter Ada Agada": ("Agada",),
}

# A surname alone is not the candidate when one of these first names comes just before it.
RELATIVES: dict[str, tuple[str, ...]] = {
    "Tinubu": ("Seyi", "Remi", "Oluremi", "Folasade", "Yinka"),
    "Obi": ("Margaret",),                    # "Obi Cubana" and the like are handled as non-matches below
    "Makinde": ("Tamunominini",),
}
NOT_CANDIDATE_AFTER = {"Obi": ("Cubana", "Nwosu", "Okonkwo")}

# Two-letter and common-word acronyms are tagged only from the party's full name, never the acronym alone.
AMBIGUOUS_ACRONYMS = frozenset({"AA", "BP", "LP", "NRM", "APP", "DLA"})

STATES: tuple[str, ...] = (
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno", "Cross River", "Delta",
    "Ebonyi", "Edo", "Ekiti", "Enugu", "Gombe", "Imo", "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi",
    "Kwara", "Lagos", "Nasarawa", "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba",
    "Yobe", "Zamfara", "FCT",
)
