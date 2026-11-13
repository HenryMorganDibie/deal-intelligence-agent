"""
Nigeria's presidential results by state, 2015, 2019 and 2023, as INEC declared them: the baseline for swings and
turnout comparisons. Votes for the two (2015, 2019) or four (2023) leading candidates, by state.

Sources and checks:
- 2023: BBC News Pidgin's state-by-state breakdown of INEC's announcements. Its PDP and NNPP states add up exactly
  to INEC's national totals; APC's states add up to 10,929 more than INEC's national 8,794,726, and LP's to 2,945
  fewer than 6,101,533. The state result sheets that would settle the difference are not published in a form we can
  read, so the state figures are kept as reported and the difference is stated in NATIONAL_2023.
- 2019 and 2015: Wikipedia's tables of INEC's declared results; every column adds up exactly to INEC's national
  totals (2019: APC 15,191,847, PDP 11,262,978; 2015: APC 15,424,921, PDP 12,853,162).
Candidates: 2023 Tinubu (APC), Atiku (PDP), Obi (LP), Kwankwaso (NNPP); 2019 Buhari (APC), Atiku (PDP); 2015
Buhari (APC), Jonathan (PDP).
"""
from __future__ import annotations

CANDIDATES = {2023: {"APC": "Bola Tinubu", "PDP": "Atiku Abubakar", "LP": "Peter Obi", "NNPP": "Rabiu Kwankwaso"},
              2019: {"APC": "Muhammadu Buhari", "PDP": "Atiku Abubakar"},
              2015: {"APC": "Muhammadu Buhari", "PDP": "Goodluck Jonathan"}}

NATIONAL_2023 = {"declared": {"APC": 8_794_726, "PDP": 6_984_520, "LP": 6_101_533, "NNPP": 1_496_687, "others": 648_474},
                 "registered": 93_469_008,
                 "state_sums_differ": {"APC": 10_929, "LP": -2_945}}
NATIONAL_2019 = {"declared": {"APC": 15_191_847, "PDP": 11_262_978}, "registered": 82_344_107, "valid": 27_324_583}
NATIONAL_2015 = {"declared": {"APC": 15_424_921, "PDP": 12_853_162}, "valid": 28_587_564}

RESULTS = {
    2023: {
        "Abia": {"APC": 8914, "PDP": 22676, "LP": 327095, "NNPP": 1239, "others": 10113},
        "Adamawa": {"APC": 182881, "PDP": 417611, "LP": 105648, "NNPP": 8006, "others": 16994},
        "Akwa Ibom": {"APC": 160620, "PDP": 214012, "LP": 132683, "NNPP": 7796, "others": 39978},
        "Anambra": {"APC": 5111, "PDP": 9036, "LP": 584621, "NNPP": 1967, "others": 13126},
        "Bauchi": {"APC": 316694, "PDP": 426607, "LP": 27373, "NNPP": 72103, "others": 10739},
        "Bayelsa": {"APC": 42572, "PDP": 68818, "LP": 49975, "NNPP": 540, "others": 3420},
        "Benue": {"APC": 310468, "PDP": 130081, "LP": 308372, "NNPP": 4740, "others": 16414},
        "Borno": {"APC": 252282, "PDP": 190921, "LP": 7205, "NNPP": 4626, "others": 10253},
        "Cross River": {"APC": 130520, "PDP": 95425, "LP": 179917, "NNPP": 1644, "others": 9462},
        "Delta": {"APC": 90183, "PDP": 161600, "LP": 341866, "NNPP": 3122, "others": 18570},
        "Ebonyi": {"APC": 42402, "PDP": 13503, "LP": 259738, "NNPP": 1661, "others": 8047},
        "Edo": {"APC": 144471, "PDP": 89585, "LP": 331163, "NNPP": 2743, "others": 13304},
        "Ekiti": {"APC": 201494, "PDP": 89554, "LP": 11397, "NNPP": 264, "others": 5462},
        "Enugu": {"APC": 4772, "PDP": 15749, "LP": 428640, "NNPP": 1808, "others": 5455},
        "Gombe": {"APC": 146977, "PDP": 319123, "LP": 26160, "NNPP": 10520, "others": 7263},
        "Imo": {"APC": 66406, "PDP": 30234, "LP": 360495, "NNPP": 1552, "others": 8693},
        "Jigawa": {"APC": 421390, "PDP": 386587, "LP": 1889, "NNPP": 98234, "others": 12431},
        "Kaduna": {"APC": 399293, "PDP": 554360, "LP": 294494, "NNPP": 92969, "others": 19037},
        "Kano": {"APC": 517341, "PDP": 131716, "LP": 28513, "NNPP": 997279, "others": 27156},
        "Katsina": {"APC": 482283, "PDP": 489045, "LP": 6376, "NNPP": 69386, "others": 11583},
        "Kebbi": {"APC": 248088, "PDP": 285175, "LP": 10682, "NNPP": 5038, "others": 10539},
        "Kogi": {"APC": 240751, "PDP": 145104, "LP": 56217, "NNPP": 4238, "others": 10480},
        "Kwara": {"APC": 263572, "PDP": 136909, "LP": 31166, "NNPP": 3141, "others": 35183},
        "Lagos": {"APC": 572606, "PDP": 75750, "LP": 582454, "NNPP": 8442, "others": 32199},
        "Nasarawa": {"APC": 172922, "PDP": 147093, "LP": 191361, "NNPP": 12715, "others": 16299},
        "Niger": {"APC": 375183, "PDP": 284898, "LP": 80452, "NNPP": 21836, "others": 34299},
        "Ogun": {"APC": 341554, "PDP": 123831, "LP": 85829, "NNPP": 2200, "others": 26710},
        "Ondo": {"APC": 369924, "PDP": 115463, "LP": 44405, "NNPP": 930, "others": 17341},
        "Osun": {"APC": 343945, "PDP": 354366, "LP": 23283, "NNPP": 713, "others": 10896},
        "Oyo": {"APC": 449884, "PDP": 182977, "LP": 99110, "NNPP": 4095, "others": 73419},
        "Plateau": {"APC": 307195, "PDP": 243808, "LP": 466272, "NNPP": 8869, "others": 62026},
        "Rivers": {"APC": 231591, "PDP": 88468, "LP": 175071, "NNPP": 1322, "others": 27199},
        "Sokoto": {"APC": 285444, "PDP": 288679, "LP": 6568, "NNPP": 1300, "others": 4884},
        "Taraba": {"APC": 135165, "PDP": 189017, "LP": 146315, "NNPP": 12818, "others": 16043},
        "Yobe": {"APC": 151459, "PDP": 198567, "LP": 2406, "NNPP": 18270, "others": 7695},
        "Zamfara": {"APC": 298396, "PDP": 193978, "LP": 1660, "NNPP": 4044, "others": 4845},
        "FCT": {"APC": 90902, "PDP": 74194, "LP": 281717, "NNPP": 4517, "others": 8741},
    },
    2019: {
        "Abia": {"APC": 85058, "PDP": 219698, "total_valid": 323291},
        "Adamawa": {"APC": 378078, "PDP": 410266, "total_valid": 811534},
        "Akwa Ibom": {"APC": 175429, "PDP": 395832, "total_valid": 578775},
        "Anambra": {"APC": 33298, "PDP": 524738, "total_valid": 605734},
        "Bauchi": {"APC": 798428, "PDP": 209313, "total_valid": 1024307},
        "Bayelsa": {"APC": 118821, "PDP": 197933, "total_valid": 321767},
        "Benue": {"APC": 347668, "PDP": 356817, "total_valid": 728912},
        "Borno": {"APC": 836496, "PDP": 71788, "total_valid": 919786},
        "Cross River": {"APC": 117302, "PDP": 295737, "total_valid": 421901},
        "Delta": {"APC": 221292, "PDP": 594068, "total_valid": 829762},
        "Ebonyi": {"APC": 90726, "PDP": 258573, "total_valid": 359131},
        "Edo": {"APC": 267842, "PDP": 275691, "total_valid": 560711},
        "Ekiti": {"APC": 219231, "PDP": 154032, "total_valid": 381132},
        "Enugu": {"APC": 54423, "PDP": 355553, "total_valid": 421014},
        "Gombe": {"APC": 402961, "PDP": 138484, "total_valid": 554203},
        "Imo": {"APC": 140463, "PDP": 334923, "total_valid": 511586},
        "Jigawa": {"APC": 794738, "PDP": 289895, "total_valid": 1106244},
        "Kaduna": {"APC": 993445, "PDP": 649612, "total_valid": 1663603},
        "Kano": {"APC": 1464768, "PDP": 391593, "total_valid": 1891134},
        "Katsina": {"APC": 1232133, "PDP": 308056, "total_valid": 1555473},
        "Kebbi": {"APC": 581552, "PDP": 154282, "total_valid": 756605},
        "Kogi": {"APC": 285894, "PDP": 218207, "total_valid": 521016},
        "Kwara": {"APC": 308984, "PDP": 138184, "total_valid": 459676},
        "Lagos": {"APC": 580825, "PDP": 448015, "total_valid": 1089567},
        "Nasarawa": {"APC": 289903, "PDP": 283847, "total_valid": 580778},
        "Niger": {"APC": 612371, "PDP": 218052, "total_valid": 851937},
        "Ogun": {"APC": 281762, "PDP": 194655, "total_valid": 564256},
        "Ondo": {"APC": 241769, "PDP": 275901, "total_valid": 555994},
        "Osun": {"APC": 347634, "PDP": 337377, "total_valid": 714682},
        "Oyo": {"APC": 365229, "PDP": 366690, "total_valid": 836531},
        "Plateau": {"APC": 468555, "PDP": 548665, "total_valid": 1034853},
        "Rivers": {"APC": 150710, "PDP": 473971, "total_valid": 642165},
        "Sokoto": {"APC": 490333, "PDP": 361604, "total_valid": 871891},
        "Taraba": {"APC": 324906, "PDP": 374743, "total_valid": 712877},
        "Yobe": {"APC": 497914, "PDP": 50763, "total_valid": 559365},
        "Zamfara": {"APC": 438682, "PDP": 125423, "total_valid": 578439},
        "FCT": {"APC": 152224, "PDP": 259997, "total_valid": 423951},
    },
    2015: {
        "Abia": {"APC": 13394, "PDP": 368303},
        "Adamawa": {"APC": 374701, "PDP": 251664},
        "Akwa Ibom": {"APC": 58411, "PDP": 953304},
        "Anambra": {"APC": 17926, "PDP": 660762},
        "Bauchi": {"APC": 931598, "PDP": 86085},
        "Bayelsa": {"APC": 5194, "PDP": 361209},
        "Benue": {"APC": 373961, "PDP": 303737},
        "Borno": {"APC": 473543, "PDP": 25640},
        "Cross River": {"APC": 28368, "PDP": 414863},
        "Delta": {"APC": 48910, "PDP": 1211405},
        "Ebonyi": {"APC": 19518, "PDP": 323653},
        "Edo": {"APC": 208469, "PDP": 286869},
        "Ekiti": {"APC": 120331, "PDP": 176466},
        "Enugu": {"APC": 14157, "PDP": 553003},
        "Gombe": {"APC": 361245, "PDP": 96873},
        "Imo": {"APC": 133253, "PDP": 559185},
        "Jigawa": {"APC": 885988, "PDP": 142904},
        "Kaduna": {"APC": 1127760, "PDP": 484085},
        "Kano": {"APC": 1903999, "PDP": 215779},
        "Katsina": {"APC": 1345441, "PDP": 98937},
        "Kebbi": {"APC": 567883, "PDP": 100972},
        "Kogi": {"APC": 264851, "PDP": 149987},
        "Kwara": {"APC": 302146, "PDP": 132602},
        "Lagos": {"APC": 792460, "PDP": 632327},
        "Nasarawa": {"APC": 236838, "PDP": 273460},
        "Niger": {"APC": 657678, "PDP": 149222},
        "Ogun": {"APC": 308290, "PDP": 207950},
        "Ondo": {"APC": 299889, "PDP": 251368},
        "Osun": {"APC": 383603, "PDP": 249929},
        "Oyo": {"APC": 528620, "PDP": 303376},
        "Plateau": {"APC": 429140, "PDP": 549615},
        "Rivers": {"APC": 69238, "PDP": 1487075},
        "Sokoto": {"APC": 671926, "PDP": 152199},
        "Taraba": {"APC": 261326, "PDP": 310800},
        "Yobe": {"APC": 446265, "PDP": 25526},
        "Zamfara": {"APC": 612202, "PDP": 144833},
        "FCT": {"APC": 146399, "PDP": 157195},
    },
}


def state_result(year: int, state: str) -> dict:
    """A state's result in a year, with each candidate's share where the total is known."""
    row = dict(RESULTS[year][state])
    total = row.get("total_valid") or (sum(v for k, v in row.items() if k != "total_valid") if year == 2023 else None)
    parties = {k: v for k, v in row.items() if k not in ("total_valid", "others")}
    out = {"year": year, "state": state, "total_valid": total, "results": [
        {"party": p, "candidate": CANDIDATES[year].get(p), "votes": v, "share": round(v / total, 4) if total else None}
        for p, v in sorted(parties.items(), key=lambda kv: -kv[1])]}
    if "others" in row:
        out["others"] = row["others"]
    return out


def baseline_2023() -> dict:
    """2023 votes by candidate, for the live tracker's reference column (2027 tickets reuse some 2023 candidates)."""
    by_name = CANDIDATES[2023]
    return {"year": 2023,
            "national": {by_name[p]: v for p, v in NATIONAL_2023["declared"].items() if p in by_name},
            "units": {s: {by_name[p]: v for p, v in r.items() if p in by_name} for s, r in RESULTS[2023].items()}}


def history(state: str | None = None) -> dict:
    """Every year's results, nationally or for one state."""
    if state:
        return {"state": state, "years": [state_result(y, state) for y in sorted(RESULTS, reverse=True)]}
    return {"national": {"2023": NATIONAL_2023, "2019": NATIONAL_2019, "2015": NATIONAL_2015},
            "states": {s: [state_result(y, s) for y in sorted(RESULTS, reverse=True)] for s in RESULTS[2023]}}
