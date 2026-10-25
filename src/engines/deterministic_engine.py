"""
Deterministic Signal Engine.

Phase 2 of the separation-of-concerns architecture.
This engine produces SignalCandidate objects using ONLY:
  - Pattern matching against a typed rule library
  - Named entity recognition (regex-based, no ML model dependency)
  - Source credibility weighting
  - Corroboration counting across independent sources

The LLM never runs until AFTER this engine confirms a candidate.
If this engine produces zero candidates → zero signals in the brief.
No exceptions.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Optional

from src.data.africa_countries import COUNTRIES, regulator_acronyms
from src.utils.clock import utcnow
from src.schemas.models import (
    SignalCandidate, SignalType, AgentState
)

# ─── Source Credibility Registry ─────────────────────────────────────────────
# Scores are 0.0–1.0. Higher = more credible as a signal source.
# Used in corroboration weighting and alpha scoring.

SOURCE_CREDIBILITY: dict[str, float] = {
    # Tier 1 — primary regulatory / exchange sources
    "SEC EDGAR":             1.00,
    "JSE SENS":              1.00,
    "NGX Group":             1.00,
    "NSE Kenya":             1.00,
    "Ghana Stock Exchange":  1.00,
    # Tier 2 — major global financial press
    "Reuters":               0.95,
    "Bloomberg":             0.95,
    "Financial Times":       0.93,
    "Wall Street Journal":   0.92,
    "CNBC":                  0.85,
    # Tier 3 — African institutional / specialist
    "IFC Press Room":        0.92,
    "AVCA":                  0.90,
    "Global Private Capital":0.88,
    "Africa PE News":        0.87,
    "PSG Capital":           0.85,
    "Zawya":                 0.84,
    "Stears":                0.83,
    "BusinessDay Nigeria":   0.80,
    "Moneyweb":              0.80,
    "BusinessLive SA":       0.79,
    "The Africa Report":     0.78,
    "African Business":      0.77,
    "Nation Africa":         0.74,
    "Nairametrics":          0.73,
    "TechCabal":             0.72,
    "The East African":      0.72,
    "Standard Media Kenya":  0.70,
    "Vanguard Nigeria":      0.68,
    "Premium Times Nigeria": 0.67,
    "Disrupt Africa":        0.65,
    "Bayport Finance":       0.65,
    # Publisher names as Google News reports them (matched as substrings)
    "Businessday":           0.80,   # Businessday NG
    "Business Daily Africa": 0.80,
    "Daily Maverick":        0.78,
    "News24":                0.74,
    "Agence Ecofin":         0.78,
    "Jeune Afrique":         0.78,
    "Financial Afrik":       0.72,
    "Sika Finance":          0.72,
    "Le Matin":              0.72,
    "Medias24":              0.74,
    "Proshare":              0.74,
    "The Guardian Nigeria":  0.72,
    "Guardian Nigeria":      0.72,
    "Punch":                 0.68,
    "ThisDay":               0.68,
    "Channels Television":   0.68,
    "The Star":              0.70,   # The Star Kenya
    "Capital FM":            0.68,
    "The Citizen":           0.68,
    "Kenyan Wall Street":    0.72,
    "Business Insider Africa": 0.72,
    "Techpoint Africa":      0.70,
    "IOL":                   0.68,
    "Ghana Business News":   0.68,
    "Graphic Online":        0.68,
    "WSJ":                   0.92,
    "The New York Times":    0.88,
    "New York Times":        0.88,
    "Washington Post":       0.85,
    "BBC":                   0.88,
    "NPR":                   0.85,
    "NBC News":              0.80,
    "CBS News":              0.80,
    "ABC News":              0.80,
    "PBS":                   0.80,
    "The Guardian":          0.82,
    "Nikkei":                0.88,
    "Axios":                 0.80,
    "Associated Press":      0.92,
    "AP News":               0.92,
    "Bloomberg Línea":       0.90,
    "The Economist":         0.90,
    "Barron's":              0.85,
    "Forbes":                0.75,
    "Business Wire":         0.85,   # company-issued press releases
    "PR Newswire":           0.85,
    "GlobeNewswire":         0.85,
    # Tier 4 — aggregators / Google News
    "Yahoo Finance":         0.60,
    "MarketWatch":           0.60,
    "Seeking Alpha":         0.55,
    "Google News Africa":    0.45,
    "Google News SA":        0.45,
    "Google News Kenya":     0.45,
}

DEFAULT_CREDIBILITY = 0.40


# ─── Pattern Rule Library ─────────────────────────────────────────────────────
# Each rule: (signal_type, [patterns], base_score)
# Patterns are case-insensitive regex. base_score sets the pre-calibration weight.
# Rules are ordered by specificity — more specific patterns score higher.

# Every African national regulator and central bank in the 54-country registry.
_AFRICAN_REGULATORS = "|".join(
    re.escape(n.lower()) for n in sorted(
        {a for a in regulator_acronyms() if len(a) >= 3}
        | {c.central_bank.split(" (")[0] for c in COUNTRIES}
        | {c.securities_regulator for c in COUNTRIES if c.securities_regulator},
        key=len, reverse=True))

SIGNAL_RULES: list[tuple[SignalType, list[str], float]] = [

    # ── M&A / Exit Activity ──
    # IPO and exit-process indicators belong here only when a concrete process is reported.
    (SignalType.MA_ACTIVITY, [
        r"\b(board|company|shareholders?)\s+(approved?|approves|authori[sz]ed|authorizes)\b.{0,50}\b(ipo|initial public offering|listing|float)\b",
        r"\b(appoints?|mandates?|hires?)\b.{0,50}\b(ipo|listing|public offering)\b.{0,30}\b(advisers?|advisors?|underwriters?|banks?)\b",
        r"\b(prepar(?:es?|ing)|plans?|planning|considering)\b.{0,35}\b(ipo|initial public offering|stock[-\s]market listing|public listing)\b",
        r"\b(ipo|initial public offering)\s+(preparations?|mandate|filing|prospectus|roadshow)\b",
    ], 0.82),
    (SignalType.MA_ACTIVITY, [
        r"\bdefinitive\s+(merger|acquisition)\b",
        # Not SEC 8-K Item 1.01 boilerplate ("Material Definitive Agreement"), which covers loans and contracts too.
        r"(?<!material )\bdefinitive\s+agreement\b",
        r"\bletter\s+of\s+intent\b",
        r"\bscheme\s+of\s+arrangement\b",
        r"\btender\s+offer\b",
        r"\bgoing\s+private\b",
        r"\bleveraged\s+buyout\b",
        r"\bspecial\s+committee\b.*\b(merger|acquisition|sale)\b",
    ], 0.90),
    (SignalType.MA_ACTIVITY, [
        r"\b(acquires?|acquired|acquiring)\b.{0,60}\b(company|corp|ltd|plc|inc|group)\b",
        r"\b(merger|acquisition)\s+(talks?|discussions?|negotiations?)\b",
        r"\b(bid|offer)\s+(for|to\s+acquire)\b",
        r"\bstrategic\s+(review|alternatives|transaction)\b",
        r"\bexclusive\s+negotiations?\b",
        r"\bboard\s+approved?\b.{0,40}\b(merger|acquisition|sale)\b",
    ], 0.75),
    (SignalType.MA_ACTIVITY, [
        r"\b(merger|acquisition|takeover|buyout)\b",
        r"\b(deal|transaction)\s+(announced?|confirmed|signed)\b",
        r"\bpotential\s+(acquirer|buyer|bidder)\b",
    ], 0.55),

    # M&A: divestitures, sale of business units, and withdrawn transactions.
    (SignalType.MA_ACTIVITY, [
        r"\b(divest(?:s|ed|ing|iture|itures)?|dispos(?:es|ed|al|als))\b.{0,50}\b(subsidiar(?:y|ies)|business\s+unit|division|stake|operations?)\b",
        r"\b(agreed|agrees|plans?|planned|announced)\b.{0,30}\b(to\s+)?(sell|sale|dispose\s+of|divest)\b.{0,50}\b(subsidiar(?:y|ies)|business|division|stake|unit)\b",
        r"\b(merger|acquisition|takeover\s+bid|sale\s+process)\b.{0,35}\b(withdrawn|terminated|abandoned|collapsed)\b",
    ], 0.78),
    # ── Credit Risk ──
    (SignalType.CREDIT_RISK, [
        r"\bcovenant\s+(breach|violation|default|waiver)\b",
        r"\bgoing\s+concern\b",
        r"\bsubstantial\s+doubt\b.{0,40}\b(continue|viability|ability)\b",
        r"\bdowngraded?\b.{0,40}\b(Moody|S&P|Fitch|GCR|rating)\b",
        r"\bcross[-\s]default\b",
        r"\bevent\s+of\s+default\b",
        r"\bdebt\s+(acceleration|called|demanded)\b",
    ], 0.92),
    (SignalType.CREDIT_RISK, [
        r"\b(credit|debt)\s+(downgrade|deterioration|pressure)\b",
        r"\bliquidity\s+(crisis|concern|risk|shortage)\b",
        r"\bdebt\s+(maturity|covenant|restructur\w*)\b",
        r"\bimpairment\s+(charge|loss|write[-\s]down)\b",
        r"\bgoodwill\s+impairment\b",
        r"\bcash\s+(burn|runway|shortage)\b",
    ], 0.78),
    (SignalType.CREDIT_RISK, [
        r"\b(credit\s+rating|leverage\s+ratio|debt[-\s]to[-\s]equity)\b",
        r"\bnet\s+debt\b.{0,30}\b(exceeded?|surpassed?|increased?)\b",
        r"\b(refinanc\w*)\b.{0,40}\b(covenant|liquidity|default|distress|higher cost|costlier|deteriorat\w*)\b",
    ], 0.55),

    (SignalType.CREDIT_RISK, [
        r"\b(cash\s+runway|runway)\b.{0,25}\b(under|less\s+than|below|only|just)\s+\d+\s+(months?|weeks?)\b",
        r"\b(missed|misses|skipped|failed\s+to\s+make)\b.{0,25}\b(debt|loan|bond|interest|coupon)\s+(payment|repayment|installments?|instalments?)\b",
        r"\b(liquidity|cash\s+flow|debt\s+service)\b.{0,30}\b(deteriorat\w*|weaken\w*|shortfall|pressure)\b",
    ], 0.88),
    # ── Distressed Asset ──
    (SignalType.DISTRESSED_ASSET, [
        r"\b(chapter\s+11|chapter\s+7|bankruptcy)\s+(fil(ed?|ing)|petition|protect)\b",
        r"\bbusiness\s+rescue\s+(proceedings?|practitioner|commenced)\b",
        r"\bprovisional\s+liquidation\b",
        r"\bjudicial\s+management\b",
        r"\breceivers?ship\b.{0,20}\b(appointed?|placed?|entered?)\b",
        r"\bvoluntary\s+administration\b",
        r"\binsolvency\s+(proceedings?|petition|filed?)\b",
    ], 0.95),
    (SignalType.DISTRESSED_ASSET, [
        # "wound up" only as insolvency ("the company was wound up"), not "ended up in".
        r"\b(liquidat(e|ion|or)|winding[\s-]up|(is|was|be|been|being|to\s+be)\s+wound\s+up|wind[\s-]up\s+(order|petition|proceedings|resolution))\b",
        r"\bdebt\s+(moratorium|standstill|restructur\w*)\b",
        r"\bcreditor\s+(protection|committee|arrangement)\b",
        r"\b(distressed|impaired)\s+(asset|portfolio|loan)\b",
    ], 0.80),
    (SignalType.DISTRESSED_ASSET, [
        r"\bnon[-\s]performing\s+(loan|asset|portfolio)\b",
        r"\bwrite[-\s]off\b",
        r"\basset\s+disposal\b.{0,30}\b(forced|compelled|required)\b",
    ], 0.60),

    (SignalType.DISTRESSED_ASSET, [
        r"\b(placed|put|entered|enters|goes|went)\b.{0,25}\b(under|into)\b.{0,25}\b(administration|receivership|business\s+rescue|judicial\s+management)\b",
        r"\b(creditors?|lenders?)\b.{0,35}\b(petition(?:ed)?\s+for|filed\s+for)\b.{0,25}\b(liquidation|winding\s+up|insolvency)\b",
        r"\b(creditors?'\s+voluntary\s+liquidation|compulsory\s+liquidation)\b",
    ], 0.88),
    # ── SEC Form 8-K item codes (filed by the company itself) ──
    (SignalType.DISTRESSED_ASSET,  [r"\bitem\s+1\.03\b"], 0.95),   # bankruptcy or receivership
    (SignalType.CREDIT_RISK,       [r"\bitem\s+2\.04\b"], 0.92),   # accelerated obligation
    (SignalType.EARNINGS_SURPRISE, [r"\bitem\s+4\.02\b"], 0.88),   # non-reliance / restatement
    (SignalType.MA_ACTIVITY,       [r"\bitem\s+(2\.01|5\.01)\b"], 0.90),  # completed deal / change of control
    (SignalType.DISTRESSED_ASSET,  [r"\bitem\s+3\.01\b"], 0.80),   # delisting notice
    (SignalType.CREDIT_RISK,       [r"\bitem\s+2\.06\b"], 0.78),   # material impairment
    (SignalType.LEADERSHIP_CHANGE, [r"\bitem\s+5\.02\b"], 0.75),   # director/officer departure or appointment

    # ── Earnings Surprise ──
    (SignalType.EARNINGS_SURPRISE, [
        r"\bprofit\s+warning\b",
        r"\b(revenue|earnings)\s+(restatement|revision|correction)\b",
        r"\bheadline\s+earnings?\b.{0,30}\b(declin\w*|fall|drop|miss|below)\b",
        r"\bguidance\s+(cut|lowered?|reduced?|withdrawn?)\b",
        r"\btrading\s+(update|statement)\b.{0,40}\b(below|miss|declin\w*)\b",
        r"\bsignificantly\s+below\s+(expectations?|guidance|consensus)\b",
    ], 0.88),
    (SignalType.EARNINGS_SURPRISE, [
        r"\b(revenue|earnings|profit|ebitda)\b.{0,20}\b(miss|below|declin\w*|fell|dropped)\b",
        r"\bloss\s+(after\s+tax|before\s+tax|per\s+share)\b",
        r"\bnegative\s+(surprise|result|performance)\b",
        r"\bbelow[-\s](plan|budget|forecast|expectations?)\b",
    ], 0.72),
    # Positive surprises (direction is set from the text in alpha_scorer.signal_direction)
    (SignalType.EARNINGS_SURPRISE, [
        r"\b(beats?|beat|topped|tops|crush(es|ed)?|exceed(s|ed)?|surpass(es|ed)?)\b.{0,30}\b(estimates?|expectations?|consensus|forecasts?)\b",
        r"\b(raises?|raised|lifts?|lifted|boosts?|boosted)\s+(its\s+)?(full[-\s]year\s+|annual\s+)?(guidance|outlook|forecast)\b",
        r"\bsignificantly\s+above\s+(expectations?|guidance|consensus)\b",
    ], 0.80),
    (SignalType.EARNINGS_SURPRISE, [
        r"\bweaker\s+(than\s+expected|results?|performance)\b",
        r"\bdisappointing\s+(results?|earnings?|revenue)\b",
    ], 0.55),

    (SignalType.EARNINGS_SURPRISE, [
        r"\b(withdraws?|withdrew|suspends?|suspended)\b.{0,30}\b(guidance|earnings\s+forecast|financial\s+outlook)\b",
        r"\b(cuts?|cut|lowers?|lowered|reduces?|reduced)\b.{0,30}\b(revenue|profit|earnings|ebitda)\s+(outlook|forecast|guidance|target)\b",
        r"\b(revenue|profit|earnings|ebitda)\s+(missed|misses|beats?|beat)\s+(analyst\s+)?(estimates?|expectations?|consensus|forecasts?)\b",
    ], 0.82),
    # ── Leadership Change ──
    (SignalType.LEADERSHIP_CHANGE, [
        r"\b(ceo|cfo|coo|cto|md|managing\s+director|chairman)\b.{0,30}(resign|depart|step.?down|terminat|dismiss)",
        r"\bsudden\s+(departure|resignation|exit).{0,30}(ceo|cfo|md|executive|director)",
        r"\babrupt\s+(departure|resignation)\b",
        r"\bmutual\s+separation\b.{0,30}\b(ceo|executive|director)\b",
    ], 0.90),
    (SignalType.LEADERSHIP_CHANGE, [
        r"\b(executive|board)\s+(reshuffle|shake[-\s]up|overhaul)",
        r"\b(independent\s+)?director\s+(resign|step.?down|depart)",
        r"\b(appointed?|named?)\s+(new\s+)?(ceo|cfo|coo|md|chairman)",
        r"\b(names|appoints|picks|taps|hires|promotes)\b.{0,40}\bas\s+(its\s+)?(new\s+|next\s+|interim\s+)?(ceo|cfo|coo|chief\s+(executive|financial|operating)|managing\s+director|md|chairman|chair)\b",
        r"\binterim\s+(ceo|cfo|md|chief\s+executive)",
        # Exchange notices: "Exit of Mrs. X from the Board", "Retirement of a Director"
        r"\b(exit|retirement|resignation|removal)\s+of\b.{0,60}\bfrom\s+the\s+board\b",
        r"\b(appointment|retirement|resignation|exit)\s+of\s+(a\s+)?(new\s+)?(non[-\s]executive\s+|independent\s+|executive\s+)?director\b",
        r"\bboard\s+(dissolution|reconstitution|restructure)\b",
    ], 0.75),
    (SignalType.LEADERSHIP_CHANGE, [
        r"\b(leadership|management)\s+(change|transition|succession)\b",
        r"\bsuccession\s+plan\b",
    ], 0.50),

    (SignalType.LEADERSHIP_CHANGE, [
        r"\b(founder|co[-\s]?founder|chief\s+executive\s+officer|chief\s+financial\s+officer)\b.{0,35}\b(resigns?|resigned|steps?\s+down|stepped\s+down|departs?|departed|quits?|quit|retires?|retired|ousted|fired|dismissed)\b",
        r"\b(resigns?|resigned|steps?\s+down|stepped\s+down|departs?|departed|quits?|quit)\b.{0,35}\b(founder|co[-\s]?founder|chief\s+executive\s+officer|chief\s+financial\s+officer)\b",
    ], 0.82),
    # ── Regulatory Action ──
    (SignalType.REGULATORY_ACTION, [
        # Include material listing/prospectus decisions, while keeping ordinary fundraising
        # announcements out of the regulatory signal category.
        r"\b(ipo|initial public offering|listing|prospectus|public offering)\b.{0,50}\b(approved?|approval|authori[sz]ed|cleared|registered|rejected|refused)\b",
        r"\b(approved?|approval|authori[sz]ed|cleared|registered|rejected|refused)\b.{0,50}\b(ipo|initial public offering|listing|prospectus|public offering)\b",
        r"\b(exchange|securities regulator|capital markets authority)\b.{0,45}\b(approves?|approved|rejects?|rejected|suspends?|suspended)\b.{0,35}\b(listing|prospectus|ipo|public offering)\b",
        r"\b(sec|fsca|cma|cbn|sarb|cbk)\b.{0,30}\b(invest(igat\w*|ment)|probe|enforcement|sanction|fine|penalty|subpoena)\b",
        r"\b(doj|ftc|competition\s+commission)\b.{0,30}\b(invest\w*|antitrust|charge|fine)\b",
        rf"\b({_AFRICAN_REGULATORS})\b.{{0,40}}\b(invest(igat\w*)|probe|sanction\w*|fine[sd]?|penalt\w*|suspend\w*|revok\w*)\b",
        rf"\b(fined|sanctioned|penali[sz]ed|suspended|censured|investigated|probed)\s+by\s+(the\s+)?({_AFRICAN_REGULATORS})\b",
        r"\blicen(c|s)e\s+(revoked?|suspended?|cancelled?)\b",
        r"\blicen(c|s)e\s+(has\s+been\s+)?(revoked?|suspended?|cancelled?|not\s+renewed)\b",
        r"\b(competition|antitrust)\s+(authority|commission|regulator)\b.{0,45}\b(blocks?|blocked|prohibits?|prohibited|prevents?|prevented)\b.{0,35}\b(acquisition|merger|deal|takeover)\b
        r"\bconsent\s+(order|decree|agreement)\b.{0,30}\b(regulat\w*|enforce\w*|penalt\w*)\b",
        r"\bcriminal\s+(charge|referral|indictment)\b.{0,30}\b(fraud|financ|securi)\b",
    ], 0.93),
    (SignalType.REGULATORY_ACTION, [
        r"\bregulatory\s+(action|enforcement|sanction|inquiry|investigation)\b",
        r"\b(fraud|misconduct|manipulation)\s+(alleg\w*|invest\w*|probe|charge)\b",
        r"\bnon[-\s]compliance\b.{0,30}\b(regulat\w*|penalt\w*|fine)\b",
        r"\bshow[-\s]cause\s+(notice|letter|order)\b",
        r"\b(market|financial)\s+(misconduct|manipulation|abuse)\b",
    ], 0.80),
    (SignalType.REGULATORY_ACTION, [
        r"\b(regulatory|compliance)\s+(concern|issue|breach|violation)\b",
        r"\bwarning\s+letter\b.{0,30}\b(regulat\w*|author\w*|govern\w*)\b",
    ], 0.58),

    # ── Debt Restructuring ──
    (SignalType.DEBT_RESTRUCTURE, [
        r"\bdebt\s+(restructur(ing|ed?)|renegotiat\w*|relief|forgiven)\b",
        r"\bhaircut\b.{0,20}\b(debt|bond|creditor|lender)\b",
        r"\bprincipal\s+(reduction|write[-\s]down|forgiven)\b",
        r"\bextension\s+of\s+(maturity|repayment|loan\s+term)\b",
        r"\bforbearance\s+(agreement|period|granted)\b",
    ], 0.88),
    (SignalType.DEBT_RESTRUCTURE, [
        r"\b(bond|loan|facility)\s+(restructur\w*|amendment|modification|waiver)\b",
        r"\bcreditor\s+(negotiation|settlement|agreement)\b",
        r"\bdeferred\s+(payment|repayment|interest)\b",
        r"\bdebt[-\s](for[-\s]equity|swap)\b",
    ], 0.75),
    (SignalType.DEBT_RESTRUCTURE, [
        r"\brefinanc\w*\b.{0,30}\b(debt|facility|bond|loan|notes?)\b",
        r"\b(debt|facility|bond|loan|notes?)\b.{0,35}\b(refinanc\w*|rollover|rolled over|maturity extension)\b",
        r"\b(refinanc\w*)\b.{0,35}\b(existing|maturing|outstanding)\s+(debt|bond|facility|loan|notes?)\b",
        r"\b(loan|bond|debt|notes?)\s+(issuance|issue|offering)\b.{0,40}\b(refinanc\w*|replace existing|retire existing|repay existing)\b",
        r"\bmaturity\s+(extension|profile|wall)\b",
    ], 0.68),

    (SignalType.DEBT_RESTRUCTURE, [
        r"\b(covenant|financial\s+covenant)\s+waiver\b",
        r"\bamend[-\s]and[-\s]extend\b",
        r"\b(exchange\s+offer|debt\s+exchange)\b.{0,30}\b(bond|debt|creditor|notes?)\b",
    ], 0.82),
    # ── Insider Activity ──
    (SignalType.INSIDER_ACTIVITY, [
        # Ownership-change and substantial-shareholder disclosures (not primary fundraising).
        r"\b(change in|changes to)\s+(beneficial\s+)?ownership\b",
        r"\bbeneficial ownership\b.{0,50}\b(disclos\w*|cross\w*|increas\w*|reduc\w*|acquir\w*|stake)\b",
        r"\b(new|largest|major|significant)\s+(?:strategic\s+)?shareholder\b",
        r"\b(stake|shareholding)\s+(acquisition|sale|disposal|increase|decrease|dilution)\b",
        r"\b(shareholder|investor)\s+(takes?|acquires?|sells?|exits?|increases?|reduces?)\b.{0,45}\b(stake|shares?|holding|ownership)\b",
        r"\b(acquir(?:es?|ed|ing)|takes?|took|buys?|bought|sells?|sold|dispos(?:es|ed|ing))\b.{0,45}\b(majority|minority|controlling|significant)\s+(?:share\s+)?stake\b",
        r"\b(cross(?:es|ed)?|exceeds?|falls?\s+below|increases?|reduces?)\b.{0,35}\b(shareholding|voting rights|beneficial ownership|disclosure threshold)\b",
        r"\b(sc\s+13[dg]|schedule\s+13[dg])\b",
        r"\bform\s+4\b.{0,30}\b(filed|purchase|sale|acquisition|disposal)\b",
        r"\bactivist\s+(investor|shareholder|campaign)\b",
        r"\bblock\s+(purchase|acquisition)\b.{0,20}\b(shares?|stake|equity)\b",
        r"\b(material|significant)\s+sharehold(ing|er)\b.{0,20}\b(disclosed|acquired|increased)\b",
    ], 0.85),
    (SignalType.INSIDER_ACTIVITY, [
        r"\binsider\s+(buying|selling|purchase|disposal)\b",
        r"\bdirector\s+(purchase|sale|dealing)\b.{0,20}\b(share|equity|stock)\b",
        r"\bstake\s+(built|increased|acquired)\b.{0,20}\b(\d+\.?\d*%|percent)\b",
        r"\bshareholder\s+(activism|campaign|requisition)\b",
        # NGX / NSE dealing notices: "DirectorsDealings", "Notification of Share Dealing by Insider"
        r"\bdirectors?'?\s*dealings?\b",
        r"\b(share|insider)\s+dealings?\b",
        r"\binsider\s+notification\b",
        r"\bproposed\s+(board|director)\s+nominee\b.{0,30}\b(activist|investor)\b",
    ], 0.72),
    (SignalType.INSIDER_ACTIVITY, [
        r"\bopen[-\s]market\s+(purchase|sale)\b",
        r"\bsignificant\s+beneficial\s+(owner|holding)\b",
    ], 0.52),

    (SignalType.INSIDER_ACTIVITY, [
        r"\b(founder|director|executive|shareholder|investor|sponsor)\b.{0,40}\b(sold|sells|disposed|disposes|reduced|reduces|trimmed|trims|exited|exits)\b.{0,40}\b(stake|shares?|holding|ownership)\b",
        r"\b(stake|shareholding|holding)\b.{0,25}\b(reduced|cut|trimmed|sold|disposed|decreased)\b",
    ], 0.78),
    # ── French: francophone Africa (BRVM, Casablanca, Tunis, Douala) ─────────
    # Same tiers and base scores as the English rules for each signal type.
    # Accent classes ([eé]) also match text with the accents stripped.
    (SignalType.MA_ACTIVITY, [
        r"\boffre\s+publique\s+d['’]?\s*(achat|[eé]change|retrait)\b",
        r"\b(opa|ope|opr)\b.{0,40}\b(sur|vis(e|ant))\b",
        r"\bprotocole\s+d['’]?\s*accord\b.{0,60}\b(acquisition|fusion|cession|rachat)\b",
        r"\btraité\s+de\s+fusion\b",
        r"\bprojet\s+de\s+fusion\b",
    ], 0.95),
    (SignalType.MA_ACTIVITY, [
        r"\b(acquiert|rach[eè]te|a\s+acquis|a\s+rachet[eé]|prend\s+le\s+contr[oô]le)\b",
        r"\b(n[eé]gociations?|discussions?)\s+exclusives?\b",
        r"\b(projet|proposition)\s+d['’]?\s*(acquisition|rachat)\b",
        r"\bcession\s+(de|d['’])\s*(sa|la|une)?\s*(participation|filiale|activit[eé])\b",
        r"\brevue\s+strat[eé]gique\b",
    ], 0.75),
    (SignalType.MA_ACTIVITY, [
        r"\b(fusion|acquisition|rachat|absorption)\b",
        r"\bentr[eé]e\s+au\s+capital\b",
    ], 0.55),
    (SignalType.MA_ACTIVITY, [
        r"\b(pr[eé]pare|pr[eé]parent|pr[eé]paration)\b.{0,35}\b(introduction en bourse|cotation|offre publique)\b",
        r"\b(introduction en bourse|cotation)\b.{0,35}\b(projet|pr[eé]paration|mandat|prospectus)\b",
    ], 0.72),
    (SignalType.REGULATORY_ACTION, [
        r"\b(prospectus|introduction en bourse|cotation|offre publique)\b.{0,45}\b(approuv[eé]|valid[eé]|autoris[eé]|rejet[eé]|refus[eé])\b",
        r"\b(approuve|approuv[eé]|valide|valid[eé]|rejette|rejet[eé])\b.{0,45}\b(prospectus|cotation|introduction en bourse)\b",
    ], 0.82),
    (SignalType.INSIDER_ACTIVITY, [
        r"\b(franchissement|franchit|d[eé]passe|passe sous)\b.{0,35}\b(seuil|participation|droits de vote)\b",
        r"\b(changement|variation)\s+de\s+(participation|d[eé]tention|propri[eé]t[eé])\b",
        r"\b(acquiert|c[eè]de|vend|renforce|all[eè]ge)\b.{0,40}\b(participation|part du capital|actions|droits de vote)\b",
    ], 0.75),
    (SignalType.DEBT_RESTRUCTURE, [
        r"\b(refinancement|refinancer|refinance)\b.{0,35}\b(dette|obligations?|cr[eé]dit|pr[eê]t)\b",
        r"\b([eé]mission obligataire|[eé]mission d['’]?obligations|pr[eê]t syndiqu[eé])\b",
        r"\b(prolongation|extension)\s+de\s+(la\s+)?maturit[eé]\b",
    ], 0.72),

    (SignalType.CREDIT_RISK, [
        r"\bd[eé]faut\s+de\s+paiement\b",
        r"\bcontinuit[eé]\s+d['’]?\s*exploitation\b",
        r"\b(d[eé]gradation|abaissement)\s+de\s+(la\s+)?notation\b",
        r"\bnotation\b.{0,30}\b(d[eé]grad[eé]e|abaiss[eé]e)\b",
        r"\bexigibilit[eé]\s+anticip[eé]e\b",
        r"\bbris\s+de\s+covenants?\b",
    ], 0.92),
    (SignalType.CREDIT_RISK, [
        r"\btensions?\s+de\s+tr[eé]sorerie\b",
        r"\bprobl[eè]mes?\s+de\s+liquidit[eé]\b",
        r"\b(d[eé]pr[eé]ciation|perte\s+de\s+valeur)\s+(d['’]?\s*actifs?|du\s+goodwill|d['’]?\s*[eé]cart\s+d['’]?\s*acquisition)\b",
        r"\bsurendettement\b",
    ], 0.78),

    (SignalType.DISTRESSED_ASSET, [
        r"\b(redressement|liquidation)\s+judiciaire\b",
        r"\bproc[eé]dure\s+(collective|de\s+sauvegarde|de\s+conciliation)\b",
        r"\b(cessation|suspension)\s+des\s+paiements\b",
        r"\bmandataire\s+(ad\s+hoc|judiciaire)\b",
        r"\badministrateur\s+(provisoire|judiciaire)\b",
    ], 0.95),
    (SignalType.DISTRESSED_ASSET, [
        r"\bliquidation\b",
        r"\bcr[eé]ances?\s+(douteuses?|en\s+souffrance|irr[eé]couvrables?)\b",
        r"\bradiation\s+de\s+la\s+cote\b",
    ], 0.80),

    (SignalType.EARNINGS_SURPRISE, [
        r"\bavertissement\s+sur\s+(les\s+)?r[eé]sultats\b",
        r"\b(r[eé]vision|r[eé]vise)\s+(à\s+la\s+baisse\s+)?(ses|des|les)\s+(pr[eé]visions|objectifs)\b.{0,20}\bbaisse\b",
        r"\b(abaisse|r[eé]duit)\s+(ses|son)\s+(pr[eé]visions|objectifs?|perspectives)\b",
        r"\bnettement\s+(inf[eé]rieurs?|en\s+de[cç]à)\s+(aux|des)\s+attentes\b",
        r"\bretraitement\s+des\s+comptes\b",
    ], 0.88),
    (SignalType.EARNINGS_SURPRISE, [
        r"\b(r[eé]sultats?|b[eé]n[eé]fices?|chiffre\s+d['’]?\s*affaires|produit\s+net\s+bancaire)\b.{0,30}\b(en\s+(baisse|recul)|recule|chute|plonge|d[eé]cro[iî]t)\b",
        r"\bperte\s+nette\b",
        r"\binf[eé]rieurs?\s+aux\s+(attentes|pr[eé]visions)\b",
    ], 0.72),
    (SignalType.EARNINGS_SURPRISE, [
        r"\b(d[eé]passe|d[eé]passent|sup[eé]rieurs?\s+aux)\s+(les\s+)?(attentes|pr[eé]visions|estimations)\b",
        r"\b(rel[eè]ve|relève|am[eé]liore|rehausse)\s+(ses|son)\s+(pr[eé]visions|objectifs?|perspectives)\b",
    ], 0.80),

    (SignalType.LEADERSHIP_CHANGE, [
        r"\b(directeur\s+g[eé]n[eé]ral|pdg|pr[eé]sident(\s+du\s+conseil)?|dg|directeur\s+financier|daf)\b.{0,40}\b(d[eé]mission(ne)?|d[eé]part|limog[eé]|r[eé]voqu[eé]|quitte)\b",
        r"\b(d[eé]mission|d[eé]part|limogeage|r[eé]vocation)\s+(du|de\s+la|de\s+son|de\s+sa)\s+(directeur\s+g[eé]n[eé]ral|pdg|pr[eé]sident|directrice\s+g[eé]n[eé]rale|dg)\b",
    ], 0.90),
    (SignalType.LEADERSHIP_CHANGE, [
        r"\b(nomm[eé]e?|nomination\s+d[eu]|nouvel(le)?)\s+(au\s+poste\s+de\s+)?(directeur\s+g[eé]n[eé]ral|directrice\s+g[eé]n[eé]rale|pdg|pr[eé]sident|dg)\b",
        r"\b(directeur\s+g[eé]n[eé]ral|pdg|dg)\s+par\s+int[eé]rim\b",
        r"\bremaniement\s+(de\s+la\s+direction|du\s+conseil)\b",
    ], 0.75),

    (SignalType.REGULATORY_ACTION, [
        r"\b(crepmf|amf[-\s]?umoa|ammc|cmf|cosumaf|bceao|beac|cobac|commission\s+bancaire|bank\s+al[-\s]maghrib)\b.{0,40}\b(sanction\w*|amende|enqu[eê]te|retrait\s+d['’]?\s*agr[eé]ment|mise\s+en\s+demeure)\b",
        r"\bretrait\s+d['’]?\s*agr[eé]ment\b",
        r"\b(sanction|amende)\s+(record|de\s+[\d\s,.]+\s*(milliards?|millions?))\b",
    ], 0.93),
    (SignalType.REGULATORY_ACTION, [
        r"\benqu[eê]te\s+(du|de\s+la|des)\s+(r[eé]gulateur|autorit[eé]|parquet|justice)\b",
        r"\b(fraude|malversations?|d[eé]tournement)\b.{0,30}\b(enqu[eê]te|poursuites?|accus\w*)\b",
        r"\bmise\s+en\s+demeure\b",
    ], 0.80),

    (SignalType.DEBT_RESTRUCTURE, [
        r"\brestructuration\s+de\s+(la\s+|sa\s+)?dette\b",
        r"\br[eé][eé]chelonnement\s+de\s+(la\s+|sa\s+)?dette\b",
        r"\babandon\s+de\s+cr[eé]ances?\b",
        r"\bmoratoire\b.{0,30}\b(dette|cr[eé]anciers|remboursement)\b",
    ], 0.88),
    (SignalType.DEBT_RESTRUCTURE, [
        r"\b(ren[eé]gociation|r[eé]am[eé]nagement)\s+de\s+(la\s+|sa\s+)?dette\b",
        r"\bconversion\s+de\s+(la\s+)?dette\s+en\s+capital\b",
        r"\baccord\s+avec\s+(les|ses)\s+cr[eé]anciers\b",
    ], 0.75),

    (SignalType.INSIDER_ACTIVITY, [
        r"\bfranchissement\s+de\s+seuil\b",
        r"\bd[eé]claration\s+de\s+(franchissement|participation)\b",
        r"\bactionnaire\s+activiste\b",
    ], 0.85),
    (SignalType.INSIDER_ACTIVITY, [
        r"\b(achat|acquisition)\s+d['’]?\s*actions\s+par\s+(un|le|des)\s+(dirigeants?|administrateurs?)\b",
        r"\b(cession|vente)\s+d['’]?\s*actions\s+par\s+(un|le|des)\s+(dirigeants?|administrateurs?)\b",
        r"\bmonte\s+(à|au)\s+(\d+[.,]?\d*\s*%|capital)\b",
    ], 0.72),

    # ── Portuguese: Mozambique (BVM), Angola (BODIVA), Cape Verde ────────────
    (SignalType.MA_ACTIVITY, [
        r"\boferta\s+p[uú]blica\s+de\s+(aquisi[cç][aã]o|troca)\b",
        r"\b(acordo|contrato)\s+(definitivo\s+)?de\s+(fus[aã]o|aquisi[cç][aã]o|compra)\b",
        r"\bprojeto\s+de\s+fus[aã]o\b",
    ], 0.95),
    (SignalType.MA_ACTIVITY, [
        r"\b(adquire|adquiriu|compra|comprou)\b.{0,60}\b(empresa|companhia|banco|grupo|participa[cç][aã]o)\b",
        r"\bnegocia[cç][oõ]es\s+exclusivas\b",
        r"\b(aquisi[cç][aã]o|fus[aã]o|incorpora[cç][aã]o)\b",
    ], 0.55),
    (SignalType.MA_ACTIVITY, [
        r"\b(prepara|preparam|preparação|preparacao)\b.{0,35}\b(oferta pública inicial|oferta publica inicial|abertura de capital|cotação|cotacao)\b",
        r"\b(oferta pública inicial|oferta publica inicial|abertura de capital)\b.{0,35}\b(projeto|preparação|preparacao|prospeto|prospecto)\b",
    ], 0.72),
    (SignalType.REGULATORY_ACTION, [
        r"\b(prospeto|prospecto|cotação|cotacao|oferta pública)\b.{0,45}\b(aprovad[oa]|autorizad[oa]|rejeitad[oa])\b",
        r"\b(aprovad[oa]|autorizad[oa]|rejeitad[oa])\b.{0,45}\b(prospeto|prospecto|cotação|cotacao|oferta pública)\b",
    ], 0.82),
    (SignalType.INSIDER_ACTIVITY, [
        r"\b(participação|participacao|direitos de voto)\b.{0,35}\b(aumenta|reduz|adquire|vende|ultrapassa|abaixo do limiar)\b",
        r"\b(adquire|vende|cede|aumenta|reduz)\b.{0,40}\b(participação|participacao|ações|acoes|direitos de voto)\b",
    ], 0.75),
    (SignalType.DEBT_RESTRUCTURE, [
        r"\b(refinanciamento|refinanciar|refinancia)\b.{0,35}\b(dívida|divida|obrigações|obrigacoes|crédito|credito|empréstimo|emprestimo)\b",
        r"\b(emissão de obrigações|emissao de obrigacoes|empréstimo sindicado|emprestimo sindicado)\b",
        r"\b(prorrogação|prorrogacao|extensão|extensao)\s+do\s+vencimento\b",
    ], 0.72),
    (SignalType.CREDIT_RISK, [
        r"\b(incumprimento|default)\b.{0,30}\b(pagamento|d[ií]vida|obriga[cç][oõ]es)\b",
        r"\b(rebaixa|rebaixamento|corte)\b.{0,30}\b(rating|nota[cç][aã]o|classifica[cç][aã]o)\b",
        r"\bcontinuidade\s+(das\s+)?opera[cç][oõ]es\b.{0,30}\b(d[uú]vida|incerteza)\b",
    ], 0.92),
    (SignalType.DISTRESSED_ASSET, [
        r"\b(fal[eê]ncia|insolv[eê]ncia|recupera[cç][aã]o\s+judicial|liquida[cç][aã]o\s+judicial)\b",
        r"\bsuspens[aã]o\s+(da\s+)?negocia[cç][aã]o\b",
    ], 0.95),
    (SignalType.EARNINGS_SURPRISE, [
        r"\b(lucros?|resultados?|receitas?)\b.{0,25}\b(caem|cai|recua|recuam|desce|descem|queda)\b",
        r"\bpreju[ií]zo\b",
        r"\b(lucros?|resultados?)\b.{0,25}\b(sobem|sobe|disparam|crescem|acima\s+das\s+(expectativas|estimativas))\b",
    ], 0.72),
    (SignalType.LEADERSHIP_CHANGE, [
        r"\b(presidente\s+(executivo|do\s+conselho)|ceo|director[a]?\s+geral|administrador[a]?\s+delegad[oa])\b.{0,40}\b(demite|demitiu|renuncia|renunciou|deixa|sai|exonerad[oa])\b",
        r"\b(demiss[aã]o|ren[uú]ncia|exonera[cç][aã]o)\s+d[oa]\s+(presidente|ceo|director[a]?\s+geral|administrador)\b",
    ], 0.90),
    (SignalType.LEADERSHIP_CHANGE, [
        r"\b(nomead[oa]|nomeia|nova?)\s+(como\s+)?(presidente\s+executivo|ceo|director[a]?\s+geral|administrador[a]?\s+delegad[oa])\b",
    ], 0.75),
    (SignalType.REGULATORY_ACTION, [
        r"\b(banco\s+de\s+mo[cç]ambique|bna|banco\s+nacional\s+de\s+angola|cmc|regulador)\b.{0,40}\b(multa|san[cç][aã]o|sancion\w+|investiga[cç][aã]o|suspende|revoga)\b",
        r"\b(multad[oa]|multa\s+de)\b",
    ], 0.80),
    (SignalType.DEBT_RESTRUCTURE, [
        r"\breestrutura[cç][aã]o\s+(da|de)\s+d[ií]vida\b",
        r"\breescalonamento\s+(da|de)\s+d[ií]vida\b",
    ], 0.88),
    (SignalType.INSIDER_ACTIVITY, [
        r"\bparticipa[cç][aã]o\s+qualificada\b",
        r"\btransa[cç][oõ]es\s+de\s+dirigentes\b",
    ], 0.85),

    # ── Arabic: Egypt (EGX), Maghreb, Gulf-listed African names ───────────────
    # Arabic attaches prefixes (al-, wa-, bi-, li-) to the word, so no \b before it.
    (SignalType.MA_ACTIVITY, [
        r"عرض\s+(شراء|استحواذ)\s+(إجباري|اجباري)?",
        r"(?:و|ف|ب|ل|ك)?(?:ال)?(استحواذ|اندماج)\s+(على|مع)\s+",
    ], 0.90),
    (SignalType.MA_ACTIVITY, [
        r"(?:و|ف|ب|ل|ك)?(?:ال)?(استحواذ|اندماج|صفقة\s+شراء)",
    ], 0.55),
    (SignalType.CREDIT_RISK, [
        r"(?:و|ف|ب|ل|ك)?(?:ال)?(تعثر|تخلف)\s+عن\s+(سداد|الدفع)",
        r"(?:و|ف|ب|ل|ك)?(?:ال)?(خفض|تخفيض)\s+(ال)?تصنيف(ها|ه)?\s+(ال)?ائتماني",
    ], 0.92),
    (SignalType.DISTRESSED_ASSET, [
        r"(?:و|ف|ب|ل|ك)?(?:ال)?(إفلاس|افلاس|إعسار|تصفية\s+(إجبارية|قضائية)?)",
        r"(?:و|ف|ب|ل|ك)?(?:ال)?(إيقاف|ايقاف|تعليق)\s+(ال)?تداول",
    ], 0.95),
    (SignalType.EARNINGS_SURPRISE, [
        r"(?:و|ف|ب|ل|ك)?(?:ال)?(أرباح|ارباح|إيرادات|ايرادات)\S*\s+.{0,20}(تتراجع|تراجع|تنخفض|انخفاض|هبوط)",
        r"(?:و|ف|ب|ل|ك)?(?:ال)?(خسائر|خسارة)\s+(صافية)?",
        r"(?:و|ف|ب|ل|ك)?(?:ال)?(أرباح|ارباح)\S*\s+.{0,20}(ترتفع|ارتفاع|قفزة|تقفز|تتجاوز\s+التوقعات)",
    ], 0.72),
    (SignalType.LEADERSHIP_CHANGE, [
        r"(?:و|ف|ب|ل|ك)?(?:ال)?(استقالة|إقالة|اقالة)\s+(ال)?(رئيس\s+(ال)?تنفيذي|عضو\s+(ال)?منتدب|رئيس\s+مجلس\s+(ال)?إدارة)(?:(?:\s+جديد(?:ة)?)?(?:\s+(?:لشركة|للشركة|في\s+شركة|بشركة|ل))?\s+\S+)?",
        r"(?:و|ف|ب|ل|ك)?(?:ال)?(تعيين)\s+.{0,30}(رئيس(ا|اً)?\s+(ال)?تنفيذي(ا|اً)?|عضو(ا|اً)?\s+(ال)?منتدب(ا|اً)?)(?:(?:\s+جديد(?:ة)?)?(?:\s+(?:لشركة|للشركة|في\s+شركة|بشركة|ل))?\s+\S+)?",
    ], 0.90),
    (SignalType.REGULATORY_ACTION, [
        r"(هيئة\s+(ال)?رقابة\s+(ال)?مالية|(ال)?بنك\s+(ال)?مركزي|(ال)?بورصة).{0,40}(غرامة|عقوبة|تحقيق|إيقاف|شطب)",
        r"(?:و|ف|ب|ل|ك)?(?:ال)?(غرامة|عقوبة)\s+(مالية)?",
    ], 0.80),
    (SignalType.DEBT_RESTRUCTURE, [
        r"(?:و|ف|ب|ل|ك)?(?:ال)?(إعادة|اعادة)\s+(ال)?هيكلة\s+(ال)?(ديون|مديونية)",
        r"(?:و|ف|ب|ل|ك)?(?:ال)?(جدولة)\s+(ال)?(ديون|مديونية)",
    ], 0.88),
    (SignalType.INSIDER_ACTIVITY, [
        r"(?:و|ف|ب|ل|ك)?(?:ال)?(شراء|بيع)\s+.{0,20}(أسهم|اسهم)\s+.{0,20}(عضو|رئيس|مسؤول|أحد\s+المطلعين)",
    ], 0.72),
]

# ─── Named Entity Patterns ────────────────────────────────────────────────────
COMPANY_SUFFIX_PATTERN = re.compile(
    r'\b([A-Z][a-zA-Z\s&\'\-\.]{2,40}?)\s+(Corp|Corporation|Ltd|Limited|plc|PLC|Inc|LLC|Group|Holdings?|Bank|Financial|Capital|Fund)\b'
)
AMOUNT_PATTERN = re.compile(
    r'\$[\d,\.]+\s*(million|billion|M|B|bn)?\b|\b[\d,\.]+\s*(million|billion)\s+(dollars?|USD|NGN|ZAR|KES|GHS)\b',
    re.IGNORECASE
)
PERCENTAGE_PATTERN = re.compile(r'\d+\.?\d*\s*%')


def _classify_event_subtype(signal_type: SignalType, text: str) -> str:
    """Assign a stable, specific event label without changing the canonical signal type."""
    value = (text or "").lower()
    rules: dict[SignalType, list[tuple[str, tuple[str, ...]]]] = {
        SignalType.MA_ACTIVITY: [
            ("divestiture", ("divestiture", "divests", "divested", "divesting", "dispose of a subsidiary", "sale of a division", "sells its subsidiary", "agreed to sell", "cession de filiale")),
            ("transaction_withdrawn", ("acquisition withdrawn", "acquisition was withdrawn", "merger withdrawn", "deal terminated", "takeover bid withdrawn", "acquisition abandoned")),
            ("ipo_preparation", ("ipo", "initial public offering", "introduction en bourse", "cotation", "oferta pública inicial", "oferta publica inicial", "abertura de capital", "listing preparations", "roadshow", "prospectus")),
            ("merger", ("merger", "merges with", "fusion")),
            ("acquisition", ("acquisition", "acquires", "acquired", "takeover", "rachat", "acquiert", "cession de contrôle", "aquisição", "adquire", "buyout")),
            ("strategic_review", ("strategic review", "strategic alternatives", "sale process")),
            ("exit_process", ("exit process", "exploring a sale", "sale of the company")),
        ],
        SignalType.CREDIT_RISK: [
            ("cash_runway", ("cash runway", "runway of less than", "runway below")),
            ("missed_payment", ("missed debt payment", "missed coupon payment", "skipped interest payment", "failed to make a debt payment")),
            ("covenant_breach", ("covenant breach", "breached its covenant", "waiver request", "bris de covenant", "bris de covenants")),
            ("liquidity_stress", ("liquidity crisis", "liquidity shortfall", "cash crunch", "liquidity stress", "tensions de trésorerie", "tensions de tresorerie", "problèmes de liquidité", "problemes de liquidite")),
            ("default", ("defaulted", "event of default", "missed debt payment", "payment default", "défaut de paiement", "defaut de paiement", "incumprimento")),
            ("rating_downgrade", ("downgrade", "rating cut", "credit rating lowered")),
            ("impairment", ("impairment", "write-down", "write down")),
        ],
        SignalType.DISTRESSED_ASSET: [
            ("receivership_or_administration", ("receivership", "placed under administration", "entered administration", "business rescue")),
            ("insolvency", ("insolvency", "insolvent", "bankruptcy", "bankrupt", "insolvabilité", "insolvabilite", "insolvência", "insolvencia")),
            ("liquidation", ("liquidation", "liquidator", "winding-up", "winding up", "liquidation judiciaire", "liquidação")),
            ("business_rescue", ("business rescue", "administration", "administrator appointed")),
            ("going_concern", ("going concern", "material uncertainty")),
            ("distressed_asset_sale", ("distressed sale", "forced sale", "asset fire sale")),
        ],
        SignalType.EARNINGS_SURPRISE: [
            ("guidance_revision", ("withdraws guidance", "withdrew guidance", "withdraws its full-year earnings guidance", "withdrew its full-year earnings guidance", "cuts guidance", "guidance cut", "lowers outlook")),
            ("profit_warning", ("profit warning", "earnings warning", "profit alert")),
            ("earnings_miss", ("missed estimates", "below expectations", "profit fell short", "earnings miss")),
            ("earnings_beat", ("beat estimates", "above expectations", "earnings beat", "profit jumped")),
            ("results_update", ("results", "earnings", "revenue", "profit")),
        ],
        SignalType.LEADERSHIP_CHANGE: [
            ("founder_departure", ("founder resigns", "founder resigned", "founder steps down", "founder stepped down", "founder departs", "founder departed", "co-founder resigns", "co-founder steps down")),
            ("executive_departure", ("resigns", "resigned", "steps down", "stepped down", "quits", "ousted", "fired")),
            ("executive_appointment", ("appoints", "appointed", "names", "named", "hires", "new ceo", "new cfo")),
            ("board_change", ("board member", "director", "chairman", "chairwoman", "board of directors")),
        ],
        SignalType.REGULATORY_ACTION: [
            ("licence_action", ("licence revoked", "license revoked", "licence suspended", "license suspended", "licence has been suspended", "license has been suspended", "licence not renewed", "license not renewed")),
            ("listing_rejection", ("rejected the listing", "listing application rejected", "prospectus rejected", "refused listing", "prospectus rejeté", "prospectus rejete", "cotation refusée", "cotation refusee")),
            ("listing_approval", ("approved the listing", "listing approved", "prospectus approved", "approved the prospectus", "prospectus approuvé", "prospectus approuve", "admission à la cote", "admission a la cote")),
            ("enforcement_or_sanction", ("sanction", "fine", "penalty", "enforcement", "suspended")),
            ("investigation", ("investigation", "investigates", "probe", "inquiry")),
        ],
        SignalType.DEBT_RESTRUCTURE: [
            ("covenant_waiver", ("covenant waiver", "financial covenant waiver", "amend-and-extend")),
            ("refinancing", ("refinanc", "refinanced", "refinancing", "refinancement", "refinanciamento")),
            ("debt_for_equity", ("debt-for-equity", "debt for equity", "debt conversion")),
            ("maturity_extension", ("maturity extension", "extends maturities", "extended maturity")),
            ("bond_issuance", ("bond issuance", "issues bonds", "issued bonds", "bond offering", "émission obligataire", "emission obligataire", "émission d’obligations", "emissão de obrigações")),
            ("loan_facility", ("syndicated loan", "loan facility", "credit facility", "term loan", "prêt syndiqué", "pret syndique", "crédit syndiqué", "credito sindicado", "empréstimo sindicado", "emprestimo sindicado")),
            ("debt_restructuring", ("debt restructuring", "restructures debt", "restructuring agreement")),
        ],
        SignalType.INSIDER_ACTIVITY: [
            ("beneficial_ownership_change", ("beneficial ownership", "disclosure threshold", "voting rights", "shareholding", "franchissement de seuil", "déclaration de participation", "declaracao de participacao", "participação acionista", "participacao acionista")),
            ("stake_disposal", ("founder sells", "founder sold", "director sells", "director sold", "reduces its stake", "stake reduced", "stake disposal", "disposes of stake", "sold its stake", "sells stake", "stake sale", "cède sa participation", "cede sa participation", "cession de participation", "vende participação", "vende participacao")),
            ("stake_acquisition", ("acquires stake", "takes a stake", "buys stake", "increases its stake", "stake acquisition", "acquiert une participation", "monte au capital", "adquire participação", "adquire participacao")),
            ("insider_selling", ("insider selling", "director sells", "insider sold", "director dealing sale")),
            ("insider_buying", ("insider buying", "director buys", "insider bought", "director dealing purchase")),
            ("activist_position", ("activist investor", "activist stake", "campaigning shareholder")),
        ],
    }
    for subtype, phrases in rules.get(signal_type, []):
        if any(phrase in value for phrase in phrases):
            return subtype
    return "unspecified"


def _extract_event_attributes(text: str) -> dict[str, Any]:
    """Extract simple, auditable event facts; never infer a value absent from source text."""
    attributes: dict[str, Any] = {}
    amounts = [match.group(0).strip() for match in AMOUNT_PATTERN.finditer(text or "")]
    percentages = [match.group(0).strip() for match in PERCENTAGE_PATTERN.finditer(text or "")]
    if amounts:
        attributes["amount_mentions"] = list(dict.fromkeys(amounts))[:5]
    if percentages:
        attributes["percentage_mentions"] = list(dict.fromkeys(percentages))[:5]
    currencies = re.findall(r"\b(?:USD|US\$|EUR|GBP|NGN|ZAR|KES|GHS|EGP|XOF|XAF)\b|[$€£₦]", text or "", re.IGNORECASE)
    if currencies:
        attributes["currency_mentions"] = list(dict.fromkeys(currencies))[:5]
    role_match = re.search(r"\b(CEO|CFO|COO|CTO|chairman|chairwoman|chair|president|managing director)\b", text or "", re.IGNORECASE)
    if role_match:
        attributes["role_mentioned"] = role_match.group(0)
    return attributes

def _extract_entities(text: str) -> list[str]:
    """Extract named entities (companies, amounts, percentages) from text."""
    entities = []
    for m in COMPANY_SUFFIX_PATTERN.finditer(text):
        entities.append(m.group(0).strip())
    for m in AMOUNT_PATTERN.finditer(text):
        entities.append(m.group(0).strip())
    for m in PERCENTAGE_PATTERN.finditer(text):
        entities.append(m.group(0).strip())
    return list(dict.fromkeys(entities))[:10]  # deduplicate, cap at 10


# ── Headline phrasing ────────────────────────────────────────────────────────
# News headlines state events with active verbs and job titles that the filing-oriented
# rules above miss ("S&P downgrades X", "SEC fines X", "CEO quits", "files for bankruptcy").
# Measured on the attribution suite (evaluation/attribution); same tiers as above.
_ROLE = (r"(ceo|cfo|coo|cto|md|managing\s+director|chairman|chairwoman|chair|president|"
         r"chief\s+(executive|financial|operating|technology)(\s+officer)?|finance\s+director|group\s+ceo)")
_AGENCY = r"(moody'?s|s&p|standard\s+&\s+poor'?s|fitch|gcr|global\s+credit\s+rating|agusto|dbrs|r&i)"
_MONEY = r"(\$|us\$|€|£|₦|n\d|r\d|ksh|egp|usd|eur|naira|rand|dirhams?|euros?|dollars?|\d+(\.\d+)?\s*(m|bn|million|billion))"
# Patterns whose company is the object ("S&P downgrades Acme"): exempt from the subject-first rule.
_OBJECT_PATTERNS = {
    rf"\b{_AGENCY}\b.{{0,40}}\b(downgrades?|downgraded|cuts?|lowers?|lowered|slashes|slashed)\b",
    r"\bjoins?\b.{0,35}\bboard\b",
    r"\b(elected|named|appointed)\b.{0,50}\b(president\s+and\s+ceo|ceo|cfo|coo|chairman|president)\b",
}
HEADLINE_RULES: list[tuple[SignalType, list[str], float]] = [
    (SignalType.LEADERSHIP_CHANGE, [
        rf"\b{_ROLE}\b.{{0,30}}\b(resign\w*|quits?|quit|exits?|exited|steps?\s+down|stepped\s+down|step\s+down|retires?|retired|"
        rf"departs?|departed|ousted|fired|sacked|leaves|leaving|to\s+leave|will\s+leave)\b",
        rf"\b(resigns?|resigned|quits?|exits?|steps?\s+down|retires?)\s+as\s+(its\s+)?(group\s+)?{_ROLE}\b",
        r"\b(board\s+members?|directors?)\b.{0,35}\b(exit|exits|to\s+exit|step\s+down|steps\s+down|to\s+step\s+down|resign|resigns|resigned|depart|departed)\b",
        r"\bjoins?\b.{0,35}\bboard\b",
        r"\b(elected|named|appointed)\b.{0,50}\b(president\s+and\s+ceo|ceo|cfo|coo|chairman|president)\b",
    ], 0.90),
    (SignalType.LEADERSHIP_CHANGE, [
        rf"\b(names?|named|appoints?|appointed|picks?|taps?|hires?|promotes?)\b.{{0,40}}\bas\s+(its\s+)?(new\s+|next\s+|interim\s+|acting\s+|permanent\s+)?(group\s+)?{_ROLE}\b",
        rf"\b(names?|named|appoints?|appointed|unveils?)\s+(a\s+)?(new|next|interim|acting)\s+(group\s+)?{_ROLE}\b",
        rf"\bnew\s+(group\s+)?{_ROLE}\b.{{0,20}}\b(named|appointed|takes\s+over|starts)\b",
        r"\b(nomination|nomme|a\s+nomm[eé])\s+(d['’]\s*un\s+|un\s+)?nouve(au|l|lle)\s+(pr[eé]sident[-\s]directeur\s+g[eé]n[eé]ral|directeur\s+g[eé]n[eé]ral|pdg|dg|pr[eé]sident|directeur\s+financier)\b",
        r"\bnomm[eé]e?\s+(au\s+poste\s+de\s+)?(directeur|directrice)\s+(g[eé]n[eé]ral|financier)",
        r"\b(directeur\s+financier|daf|directeur\s+g[eé]n[eé]ral|pdg)\b.{0,20}\bquitte\s+ses\s+fonctions\b",
        r"\b(nomeia|nomeou|nomea[cç][aã]o\s+d[eo])\s+(um\s+)?nov[oa]\s+(presidente|ceo|director|administrador)",
        r"\bsa[ií]da\s+do\s+(seu\s+)?(presidente|ceo|director)",
        r"\b(presidente|ceo)\b.{0,60}\b(renunciou|renuncia|demitiu-se|deixa\s+o\s+cargo)\b",
    ], 0.75),
    (SignalType.CREDIT_RISK, [
        rf"\b{_AGENCY}\b.{{0,40}}\b(downgrades?|downgraded|cuts?|lowers?|lowered|slashes|slashed)\b",
        r"\b(downgrades?|downgraded|cuts?|lowers?|lowered)\b.{0,40}\b(rating|outlook\s+to\s+negative|to\s+(junk|ccc|cc|b-|b\+|bb-))",
        r"\b(defaults?|defaulted)\s+on\b",
        r"\b(misses?|missed|skips?|skipped)\s+(an?\s+|its\s+)?(coupon|interest|bond|debt|loan|eurobond)\s+(payments?|repayments?)\b",
        r"\b(fitch|moody'?s|s&p)\s+a\s+abaiss[eé]\b.{0,40}\bnote\b",
        r"\babaiss[eé]\w*\b.{0,30}\bla\s+note\b",
    ], 0.92),
    (SignalType.DISTRESSED_ASSET, [
        r"\b(files?|filed|filing)\s+for\s+(chapter\s+(11|7)|bankruptcy|insolvency|business\s+rescue|administration|liquidation|receivership)\b",
        r"\b(enters?|entered|placed?|placed\s+(in|into|under)|goes\s+into|went\s+into|to\s+enter|under)\s+(voluntary\s+)?(business\s+rescue|administration|liquidation|receivership)\b",
        r"\bvoluntary\s+business\s+rescue\b",
        r"\bplace\s+it\s+in\s+(voluntary\s+)?(business\s+rescue|administration|liquidation)\b",
    ], 0.95),
    (SignalType.REGULATORY_ACTION, [
        rf"\b(fined|fines?|penali[sz]ed|sanctioned|censured)\b.{{0,40}}{_MONEY}",
        r"\b(hit\s+with|slapped\s+with|faces?)\s+(a\s+|an\s+)?(\S+\s+){0,4}(fine|penalty|antitrust\s+suit|lawsuit|enforcement\s+action)\b",
        r"\b(securities\s+and\s+exchange\s+commission|competition\s+(commission|authority|tribunal)|data\s+protection\s+(commission|authority))\b.{0,60}\b(investigat\w*|probe|sanction\w*|fine[sd]?|penalt\w*|charge[sd]?)\b",
        r"\b(opened|opens|launched|launches)\s+(an?\s+)?(investigation|probe|inquiry)\s+into\b",
        r"\b(sues?|sued|charges?|charged)\b.{0,30}\b(antitrust|fraud|securities|misconduct|bribery|price[-\s]fixing)\b",
        r"\b(inflige|infligé)\s+(une\s+)?(sanction|amende)",
        r"\bcondamn[eé]e?\b.{0,40}\bamende\b",
        r"\bamende\s+de\s+[\d\s,.]+\s*(milliards?|millions?)",
    ], 0.93),
    (SignalType.INSIDER_ACTIVITY, [
        rf"\b({_ROLE}|directors?|insiders?|founder|executives?)\b.{{0,40}}\b(buys?|bought|sells?|sold|purchases?|purchased|"
        r"scoops?\s+up|scooped\s+up|offloads?|offloaded|dumps?|dumped|acquires?|acquired)\b.{0,40}\b(shares|stock|stake)\b",
        r"\bactivist\b.{0,40}\b(stake|builds|built|takes|took|discloses|disclosed)\b",
        r"\bdisclosed\s+a\s+stake\b",
        r"\b(increases?|increased|raises?|raised|boosts?|boosted)\s+(its\s+)?stake\b.{0,50}\b(in|to)\b",
    ], 0.85),
    (SignalType.DEBT_RESTRUCTURE, [
        r"\b(exchange\s+offer|consent\s+solicitation|tender\s+offer)\b.{0,40}\b(bonds?|notes?|debt|eurobonds?)\b",
        r"\b(restructure|reschedule|restructuring|rescheduling)\s+(of\s+)?(\S+\s+){0,4}(debt|loans?|bonds?|notes?|eurobonds?|obligations)\b",
        r"\bpush(es|ed)?\s+back\b.{0,30}\bmaturit",
        r"\b(talks|negotiations|agreement|agreed)\s+with\s+(its\s+)?(creditors|lenders|bondholders|noteholders)\b",
    ], 0.80),
    (SignalType.MA_ACTIVITY, [
        r"\b(agrees?|agreed|to|plans?\s+to|moves?\s+to|set\s+to)\s+(buy|acquire|sell|merge|take\s+over)\b",
        r"\b(buys?|bought|sells?|sold|acquires?|acquired|takes?|took)\s+(a\s+)?(\d+(\.\d+)?\s*(%|percent|per\s+cent|pc)\s+(stake\s+)?(of|in))",
        r"\b(sells?|sold|to\s+sell)\s+(its\s+|a\s+)?(stake|unit|subsidiary|division|business|operations?)\b",
        r"\b(sells?|sold|divests?|divested|disposes?\s+of)\b.{0,50}\b(asset|property|mall|real\s+estate|unit|subsidiary|division|business|operations?|brand|plant|mine|shaft)\b",
        r"\breceives?\s+(a\s+|an\s+)?(takeover\s+|buyout\s+|acquisition\s+)?(offer|bid|approach)\b",
        r"\bbuy\s+out\s+(the\s+)?minorit",
        r"\b(weighs|explores|exploring|considers|considering)\s+(a\s+)?(bid|sale|offer|takeover)\b",
        r"\b(in|enters?|entered)\s+(exclusive\s+)?talks\s+to\s+(buy|acquire|sell|merge)\b",
    ], 0.75),
]
SIGNAL_RULES.extend(HEADLINE_RULES)

# Denials and non-events: a clause that negates its own event is not evidence of it.
_NEGATED = re.compile(
    r"\b(denies|denied|deny|rules?\s+out|ruled\s+out|no\s+plans?\s+to|not\s+in\s+talks|will\s+not|won['’]?t|"
    r"dismiss(es|ed)?\s+(reports?|speculation|rumou?rs)|refutes?|refuted|rejects?\s+(reports?|claims?)|"
    r"no\s+(profit\s+warning|merger|takeover|deal|default|restructuring)|"
    r"d[eé]ment\w*|[eé]carte\s+toute|exclut|n['’]envisage\s+pas|nega|desmente)\b",
    re.IGNORECASE,
)


def _match_rules(text: str) -> list[tuple[SignalType, list[str], float]]:
    """
    Run all signal rules against text.
    Returns list of (signal_type, matched_patterns, base_score) for each hit.
    Takes the highest-scoring rule per signal type.
    """
    text_lower = text.lower()
    best: dict[SignalType, tuple[list[str], float]] = {}

    for signal_type, patterns, base_score in SIGNAL_RULES:
        if _vetoed(signal_type, base_score, text_lower):
            continue
        matched = []
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                matched.append(pattern)
        if not matched:
            continue
        # Keep highest base_score per signal type
        existing = best.get(signal_type)
        if existing is None or base_score > existing[1]:
            best[signal_type] = (matched, base_score)

    return [(sig_type, patterns, score) for sig_type, (patterns, score) in best.items()]


# Words too generic to identify a company on their own.
_GENERIC_NAME_WORDS = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited",
    "plc", "llc", "lp", "holdings", "holding", "group", "the", "and", "of",
    "bank", "financial", "capital", "international", "global", "trust", "sa", "ag", "nv",
}
# Names that are ordinary words once "Group" or "Bank" is dropped ("Equity Group", "Access
# Holdings", "Standard Bank"): they must appear with a corporate word, and not straight after
# another proper name ("Star Equity Holdings" is not Equity Group).
_COMMON_NAME_WORDS = {
    "equity", "access", "standard", "first", "union", "national", "united", "sterling", "fidelity",
    "guaranty", "providence", "unity", "heritage", "premier", "prime", "summit", "diamond", "keystone",
    "african", "star", "royal", "liberty", "imperial", "investment", "development", "commercial",
}
_CORPORATE_WORDS = sorted(_GENERIC_NAME_WORDS - {"the", "and", "of", "sa", "ag", "nv"})
_PRECEDING_NAME = re.compile(r"(?:^|[\s(])([A-Z][\w&.-]*)\s+$")
_NOT_A_NAME = {"lender", "bank", "kenya", "kenyan", "nigeria", "nigerian", "lenders", "banks", "as", "how", "why", "after",
               "the", "with", "by", "and", "at", "from", "for", "to", "in", "on", "of", "said"}


class _QualifiedName:
    """A pattern for a common-word company name that skips matches preceded by another proper name."""

    def __init__(self, word: str):
        corp = "|".join(_CORPORATE_WORDS)
        self.pattern = re.compile(rf"\b{re.escape(word)}\W+(?:{corp})\b", re.IGNORECASE)

    def search(self, text: str, pos: int = 0) -> Optional[re.Match]:
        for m in self.pattern.finditer(text, pos):
            prev = _PRECEDING_NAME.search(text[max(0, m.start() - 40):m.start()])
            if prev and not re.search(r"['’]s$", prev.group(1)) and prev.group(1).lower() not in _NOT_A_NAME:
                continue
            return m
        return None


def _cik_number(cik: Optional[str]) -> Optional[int]:
    try:
        return int(str(cik))
    except (TypeError, ValueError):
        return None


def _country_words() -> tuple[set[str], str]:
    from src.data.africa_countries import COUNTRIES
    names = sorted({c.name for c in COUNTRIES} | {"South Africa", "Ivory Coast", "Cote d'Ivoire", "DRC", "Congo"},
                   key=len, reverse=True)
    return {w.lower() for n in names for w in re.findall(r"[^\W_]+", n)}, "|".join(re.escape(n) for n in names)


_COUNTRY_WORDS, _COUNTRY_ALT = _country_words()


# ─── Source independence ─────────────────────────────────────────────────────
# Corroboration counts independent stories, not articles: a wire story republished by Yahoo
# Finance, MarketScreener and Investing.com is one source. Near-identical headlines (token overlap
# of 0.6 or more) and reports crediting the same wire service are one story; filings count once
# per accession number.
_WIRES = re.compile(r"\b(reuters|bloomberg|afp|agence\s+france[-\s]presse|associated\s+press|\(ap\)|apo\s+group|"
                    r"dow\s+jones|xinhua|anadolu|business\s+wire|pr\s+newswire|globe\s*newswire|accesswire)\b", re.IGNORECASE)
_STOP = {"the", "and", "for", "with", "from", "that", "this", "after", "over", "into", "its", "des", "les", "pour", "dans"}


def _story_tokens(text: str) -> set[str]:
    head = re.split(r"\s[-–|]\s", text or "", maxsplit=1)[0]
    return {w for w in re.findall(r"[^\W_]{3,}", head.lower()) if w not in _STOP}


class _StoryClusters:
    def __init__(self) -> None:
        self._clusters: list[tuple[set[str], str]] = []
        self.duplicates = 0

    def key(self, c: "SignalCandidate") -> str:
        if c.source_type == "filing":
            return f"filing:{c.filing_reference or c.source_url or c.source_name}"
        toks = _story_tokens(c.source_text)
        wire = _WIRES.search(c.source_name or "") or _WIRES.search(c.source_text or "")
        if wire:                          # the wire's own story and every copy crediting it
            k = "wire:" + re.sub(r"\W+", "", wire.group(1).lower())
            if any(k == other for _, other in self._clusters):
                self.duplicates += 1
            else:
                self._clusters.append((toks, k))
            return k
        for other, k in self._clusters:
            if toks and other and len(toks & other) / len(toks | other) >= 0.6:
                self.duplicates += 1
                return k
        k = f"story:{len(self._clusters)}"
        self._clusters.append((toks, k))
        return k


def _company_matchers(*names: Optional[str], ticker: Optional[str] = None) -> list[re.Pattern]:
    """
    Word-boundary patterns that identify the target company in free text.

    A multi-word name matches only as a phrase (legal suffixes dropped), so
    "Guaranty Trust Bank" does not match an article that merely says "bank".
    A ticker matches only in upper case and only if it is at least 3 characters.
    """
    patterns: list[re.Pattern] = []
    for name in names:
        if not name:
            continue
        words = re.findall(r"[^\W_]+|&", name)          # Unicode: Moçambique, طلعت مصطفى
        while words and words[-1].lower() in _GENERIC_NAME_WORDS:
            words.pop()
        if not words or (len(words) == 1 and words[0].lower() in _GENERIC_NAME_WORDS):
            continue
        if len(words) == 1 and words[0].lower() in _COMMON_NAME_WORDS:
            patterns.append(_QualifiedName(words[0]))
            continue
        phrase = r"\W+".join(re.escape(w) for w in words)
        # Not a product named after the company ("Boeing 737", "Airbus A320", "Toyota RAV4"), and not a
        # country subsidiary of a parent ("MTN Nigeria", "Sanlam Kenya" are not "MTN Group", "Sanlam").
        sub = "" if any(w.lower() in _COUNTRY_WORDS for w in words) else rf"|\s+(?:{_COUNTRY_ALT})\b"
        patterns.append(re.compile(rf"\b{phrase}\b(?!\s*-?\d{{2,}}|\s+[A-Z]{{1,3}}-?\d{sub})", re.IGNORECASE))
    base = ticker.split(".")[0] if ticker else None     # GTCO.LG -> GTCO
    if base and len(base) >= 3:
        patterns.append(re.compile(rf"\b{re.escape(base.upper())}\b"))
    return patterns


def _mentions_company(text: str, matchers: list[re.Pattern]) -> bool:
    return not matchers or any(m.search(text) for m in matchers)


# ─── Subject attribution for news ─────────────────────────────────────────────
# A news item names the target, but is the trigger about the target? A rule only
# counts if its trigger sits in the same clause as the company's name. Headlines
# are split at separators and subordinating words, so in "Vodacom lifts outlook
# as Safaricom deal reshapes growth" the outlook clause does not name Safaricom.
_CLAUSE_BREAK = re.compile(
    r"\s+[-–—]\s+|[;:|]|(?<!\b(?:Mr|Ms|Dr|St|Co|No|MR|MS|DR|ST|CO|NO)\.)(?<!\b(?:Mrs|MRS|Ltd|LTD|Inc|INC|Plc|PLC)\.)(?<=[.!?])\s+"
    # "as" joins clauses ("lifts outlook as rival deal closes") but also names roles ("named Ade as CEO").
    r"|\sas\s(?!(?:its|his|her|their|the|a|an|new|interim|acting|permanent|chief|ceo|cfo|coo|chairman|chair|"
    r"chairperson|md|managing|president|director|head|group|non|independent|executive|company)\b)"
    r"|\s(?:after|amid|while|following|despite|before|since|whereas|although|though|but|however)\s"
    r"|\s(?:apr[eè]s|alors\s+que|malgr[eé]|tandis\s+que|avant|depuis|suite\s+[àa]|car|puisque|mais)\s"
    r"|\s(?:ap[oó]s|apesar\s+de|enquanto|depois\s+de|antes\s+de)\s"
    r"|\s(?:بعد|رغم|بينما|قبل|في\s+ظل)\s",
    re.IGNORECASE,
)
# Events that belong to the clause's subject: the company must be named before the
# trigger ("Acme beats estimates", not "Rival beats estimates on Acme deal"; "Rival
# faces cash burn and Acme deal risk" is the rival's credit, not Acme's).
_SUBJECT_ONLY_TYPES = {SignalType.EARNINGS_SURPRISE, SignalType.LEADERSHIP_CHANGE, SignalType.CREDIT_RISK}

# Good news that only shares vocabulary with a risk rule: "GCR upgrades Acme to
# its highest credit rating" mentions a credit rating but is not credit risk. A
# veto only blocks that type's weaker patterns (base score below 0.9); explicit
# distress language ("downgraded by Moody's", "event of default") still fires.
_POSITIVE_VETO = {
    SignalType.CREDIT_RISK: re.compile(
        r"\b(upgrad\w*|affirm\w*|outlook\s+(raised|to\s+positive|revised\s+to\s+positive)"
        r"|rel[eè]ve\w*\s+(la\s+|sa\s+)?notation|rehauss\w*|perspective\s+positive)\b",
        re.IGNORECASE,
    ),
}
_VETO_MAX_SCORE = 0.9


def _vetoed(sig_type: SignalType, base_score: float, text: str) -> bool:
    veto = _POSITIVE_VETO.get(sig_type)
    return bool(veto and base_score < _VETO_MAX_SCORE and veto.search(text))


# A clause with no company name can still be about the company when it refers back
# with a pronoun ("Shares of Acme jump after it beats estimates"). It inherits the
# previous clause's subject only when the company led that clause, so in "Rival
# buys Acme stake after it beats estimates" the "it" stays with Rival.
_ROLE_NOUNS = (r"company|group|firm|bank|lender|insurer|miner|operator|telco|retailer|carrier|airline|explorer|"
               r"producer|maker|planemaker|chipmaker|carmaker|automaker|brewer|refiner|conglomerate|giant|"
               r"manufacturer|developer|utility|grocer|chain|platform|fintech|startup|provider|supplier")
_BACK_REFERENCE = re.compile(
    rf"\b(it|its|the\s+([\w&-]+\s+){{0,2}}({_ROLE_NOUNS})"
    r"|il|elle|la\s+(soci[eé]t[eé]|banque|compagnie|firme)|l['’]\s*op[eé]rateur|le\s+(groupe|holding|op[eé]rateur))(?=\W|$)",
    re.IGNORECASE,
)
_LEADING_SUBJECT_PREFIX = re.compile(
    r"^\W*((shares|stock|stocks)\s+(of|in)\s+|(l['’]\s*)?action\s+(de\s+|d['’]\s*)|le\s+titre\s+(de\s+|d['’]\s*)|qu['’]\s*)?$",
    re.IGNORECASE,
)


def _leads_clause(clause: str, mention: Optional[int]) -> bool:
    return mention is not None and bool(_LEADING_SUBJECT_PREFIX.match(clause[:mention]))


def _is_label(clause: str, matchers: list[re.Pattern]) -> bool:
    """A clause that is just the company's name (plus at most two words such as
    'plc' or 'Q3'), as in 'Acme: CEO resigns' or 'Sonatel : OPA sur ...'."""
    for p in matchers:
        m = p.search(clause)
        if m and _LEADING_SUBJECT_PREFIX.match(clause[:m.start()]):
            return len((clause[:m.start()] + " " + clause[m.end():]).split()) <= 2
    return False


def _clauses(text: str) -> list[str]:
    return [c for c, _ in _clauses_with_breaks(text)]


_LABEL_BREAK = re.compile(r"^\s*([:|]|[-–—])\s*$")


def _clauses_with_breaks(text: str) -> list[tuple[str, bool]]:
    """Clauses, each with whether it ends at a label separator (':', '|', ' - ')."""
    out: list[tuple[str, bool]] = []
    pos = 0
    for m in _CLAUSE_BREAK.finditer(text):
        clause = text[pos:m.start()].strip()
        if clause:
            out.append((clause, bool(_LABEL_BREAK.match(m.group(0)))))
        pos = m.end()
    tail = text[pos:].strip()
    if tail:
        out.append((tail, False))
    return out


def _first_mention(text: str, matchers: list[re.Pattern]) -> Optional[int]:
    starts = [m.start() for p in matchers for m in [p.search(text)] if m]
    return min(starts) if starts else None


def match_rules_for_target(
    text: str, matchers: list[re.Pattern]
) -> list[tuple[SignalType, list[str], float]]:
    """
    Rule hits whose trigger is attributed to the target company: the trigger must be
    in a clause that names the company (or refers back to it, when the company led
    the previous clause), and for subject-owned events (earnings, leadership,
    credit) the company must be named before the trigger.
    """
    if not matchers:
        return _match_rules(text)
    best: dict[SignalType, tuple[list[str], float]] = {}
    previous_led = previous_label = False
    for clause, ends_at_label_break in _clauses_with_breaks(text):
        mention = _first_mention(clause, matchers)
        led = _leads_clause(clause, mention)
        label = ends_at_label_break and _is_label(clause, matchers)
        if mention is None and previous_label:
            mention = 0                  # 'Acme: CEO resigns' - the clause is about Acme
        elif mention is None and previous_led:
            back = _BACK_REFERENCE.search(clause)
            if back and _leads_clause(clause, back.start()):
                mention = back.start()
            elif re.match(r"\s*(also\s+|then\s+)?[a-z]+(s|ed)\b", clause):
                mention = 0              # 'Acme denies talks but confirms CFO exit': the subject carries over
                led = True
        previous_led, previous_label = led, label
        if mention is None:
            continue
        if _NEGATED.search(clause):
            continue                     # 'Acme denies takeover approach', 'CEO will not resign'

        for sig_type, patterns, base_score in SIGNAL_RULES:
            if _vetoed(sig_type, base_score, clause):
                continue
            matched = []
            for pattern in patterns:
                m = re.search(pattern, clause, re.IGNORECASE)
                if not m:
                    continue
                # Subject-owned events: the company comes first ("Acme beats estimates"), or
                # sits inside the matched phrase ("Earnings at Acme fell", "أرباح حديد عز ترتفع").
                # The second form only when the phrase opens the clause, so in "Rival names
                # Acme veteran as CEO" the subject is still Rival.
                inside = mention < m.end() and _LEADING_SUBJECT_PREFIX.match(clause[:m.start()])
                if sig_type in _SUBJECT_ONLY_TYPES and mention > m.start() and not inside and pattern not in _OBJECT_PATTERNS:
                    continue
                matched.append(pattern)
            if matched and (sig_type not in best or base_score > best[sig_type][1]):
                best[sig_type] = (matched, base_score)
    return [(t, ps, sc) for t, (ps, sc) in best.items()]


_CREDIBILITY_KEYS = sorted(
    ((re.compile(r"(?<![A-Za-z0-9])" + re.escape(k) + r"(?![A-Za-z0-9])", re.IGNORECASE), v)
     for k, v in SOURCE_CREDIBILITY.items()),
    key=lambda kv: -len(kv[0].pattern),
)


def _source_credibility(source_name: str) -> float:
    """Credibility of a publisher: the longest table name found as a whole word in it."""
    for pattern, score in _CREDIBILITY_KEYS:
        if pattern.search(source_name or ""):
            return score
    return DEFAULT_CREDIBILITY


# Form types the exchange tools emit (see africa_tool); everything else in state.filings is from SEC EDGAR.
# Official exchange disclosure systems (see africa_tool) -> credibility source name.
# Results found by news search arrive as news items credited to their publisher.
_EXCHANGE_FORM_TYPES = {"JSE SENS": "JSE SENS", "NGX Disclosure": "NGX Group", "NSE Disclosure": "NSE Kenya"}


def _source_date(value: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.strptime((value or "")[:10], "%Y-%m-%d")
    except ValueError:
        return None


def candidate_credibility(source_type: str, source_name: str) -> float:
    """Credibility of a candidate's source. Shared by the rule engine and the alpha scorer."""
    if source_type == "filing":
        if source_name in _EXCHANGE_FORM_TYPES:
            return SOURCE_CREDIBILITY[_EXCHANGE_FORM_TYPES[source_name]]
        return SOURCE_CREDIBILITY["SEC EDGAR"]   # fetched from EDGAR by the company's CIK
    return _source_credibility(source_name)


class DeterministicSignalEngine:
    """
    Phase 2: Deterministic signal detection.
    Runs before ANY LLM call. Produces SignalCandidate objects
    from pure pattern matching + NER. No ML. No LLM. Fully reproducible.
    """

    def run(self, state: AgentState) -> AgentState:
        state.log("deterministic_engine", "Running deterministic signal engine")

        candidates: list[SignalCandidate] = []
        profile = state.company_profile
        matchers = _company_matchers(
            state.request.company_name,
            profile.name if profile else None,
            ticker=state.request.ticker or (profile.ticker if profile else None),
        )
        off_target = 0
        stale = 0
        unattributed = 0
        unattributed_titles: list[str] = []
        # Every source must fall inside the requested lookback window, whatever tool
        # produced it (undated sources are kept).
        window_end = _source_date(state.request.as_of_date) or utcnow()
        if state.request.as_of_date:
            window_end += timedelta(days=1)          # include the as-of day itself
        window_start = window_end - timedelta(days=state.request.lookback_days)

        def _too_old(date_str: Optional[str]) -> bool:
            d = _source_date(date_str)
            return d is not None and not (window_start <= d <= window_end)
        own_cik = _cik_number(state.request.cik or (profile.cik if profile else None))

        # Process filings
        for filing in state.filings:
            text = " ".join(filter(None, [
                filing.description,
                filing.raw_excerpt,
                filing.form_type,
            ]))
            if not text.strip():
                continue
            if _too_old(filing.filing_date):
                stale += 1
                continue
            # A source that never names the target cannot evidence a signal about it.
            # Only the company's own SEC filings (fetched by its CIK) are exempt; full-text
            # search hits are other companies' filings that may merely mention it.
            own_filing = own_cik is not None and _cik_number(filing.cik) == own_cik
            if not own_filing and not _mentions_company(text, matchers):
                off_target += 1
                continue
            hits = _match_rules(text)
            credibility = candidate_credibility("filing", filing.form_type)

            for sig_type, matched_patterns, base_score in hits:
                raw_score = min(base_score * credibility, 1.0)
                candidates.append(SignalCandidate(
                    signal_type=sig_type,
                    event_subtype=_classify_event_subtype(sig_type, text),
                    event_attributes=_extract_event_attributes(text),
                    matched_patterns=matched_patterns,
                    source_text=text[:500],
                    source_url=filing.document_url,
                    source_type="filing",
                    source_name=filing.form_type,
                    filing_reference=filing.accession_number,
                    source_date=_source_date(filing.filing_date),
                    entity_mentions=_extract_entities(text),
                    target_entity_matched=True,
                    corroboration_count=1,
                    raw_score=raw_score,
                ))

        # Process news items
        for news in state.news_items:
            text = f"{news.title} {news.snippet}"
            if _too_old(news.published_date):
                stale += 1
                continue
            if not _mentions_company(text, matchers):
                off_target += 1
                continue
            hits = match_rules_for_target(text, matchers)
            if not hits and _match_rules(text):
                unattributed += 1      # names the company, but the event is someone else's
                if len(unattributed_titles) < 3:
                    unattributed_titles.append(news.title)
                continue
            credibility = _source_credibility(news.source)

            for sig_type, matched_patterns, base_score in hits:
                # Relevance was mostly "does it name the company", which the gate above
                # already enforces; multiplying by it again pushed every single news
                # story to LOW. Strength now comes from the rule and the publisher.
                raw_score = min(base_score * credibility, 1.0)
                if raw_score < 0.20:
                    continue  # filter very weak news hits
                candidates.append(SignalCandidate(
                    signal_type=sig_type,
                    event_subtype=_classify_event_subtype(sig_type, text),
                    event_attributes=_extract_event_attributes(text),
                    matched_patterns=matched_patterns,
                    source_text=text[:500],
                    source_url=news.url,
                    source_type="news",
                    source_name=news.source,
                    source_date=_source_date(news.published_date),
                    entity_mentions=_extract_entities(text),
                    target_entity_matched=True,
                    corroboration_count=1,
                    raw_score=raw_score,
                ))

        # ── Corroboration counting ───────────────────────────────────────
        # Merge by canonical type AND subtype so unrelated events (e.g. an IPO
        # process and an acquisition) do not collapse into one candidate.
        merged: dict[tuple[SignalType, str], SignalCandidate] = {}
        corroboration_tracker: dict[tuple[SignalType, str], set[str]] = {}
        stories = _StoryClusters()

        for c in candidates:
            key = stories.key(c)
            group_key = (c.signal_type, c.event_subtype)
            if group_key not in merged:
                merged[group_key] = c
                corroboration_tracker[group_key] = {key}
            else:
                is_new_story = key not in corroboration_tracker[group_key]
                corroboration_tracker[group_key].add(key)
                # Take higher raw_score, merge patterns
                existing = merged[group_key]
                merged_patterns = list(dict.fromkeys(existing.matched_patterns + c.matched_patterns))
                source_urls = list(dict.fromkeys(
                    existing.corroborating_source_urls
                    + ([existing.source_url] if existing.source_url else [])
                    + (c.corroborating_source_urls if is_new_story else [])
                    + ([c.source_url] if is_new_story and c.source_url else [])
                ))
                filing_references = list(dict.fromkeys(
                    existing.corroborating_filing_references
                    + ([existing.filing_reference] if existing.filing_reference else [])
                    + (c.corroborating_filing_references if is_new_story else [])
                    + ([c.filing_reference] if is_new_story and c.filing_reference else [])
                ))
                if c.raw_score > existing.raw_score:
                    merged[group_key] = c.model_copy(update={
                        "matched_patterns": merged_patterns,
                        "corroborating_source_urls": source_urls,
                        "corroborating_filing_references": filing_references,
                        "corroboration_count": len(corroboration_tracker[group_key]),
                    })
                else:
                    merged[group_key] = existing.model_copy(update={
                        "matched_patterns": merged_patterns,
                        "corroborating_source_urls": source_urls,
                        "corroborating_filing_references": filing_references,
                        "corroboration_count": len(corroboration_tracker[group_key]),
                    })

        # Update corroboration counts
        final_candidates = []
        for group_key, candidate in merged.items():
            source_urls = list(dict.fromkeys(
                candidate.corroborating_source_urls
                + ([candidate.source_url] if candidate.source_url else [])
            ))
            filing_references = list(dict.fromkeys(
                candidate.corroborating_filing_references
                + ([candidate.filing_reference] if candidate.filing_reference else [])
            ))
            final_candidates.append(candidate.model_copy(update={
                "corroboration_count": len(corroboration_tracker[group_key]),
                "corroborating_source_urls": source_urls,
                "corroborating_filing_references": filing_references,
            }))

        # Sort by raw_score descending
        final_candidates.sort(key=lambda c: c.raw_score, reverse=True)
        state.signal_candidates = final_candidates

        state.log(
            "deterministic_engine",
            f"Engine produced {len(final_candidates)} signal candidates "
            f"({off_target} source(s) skipped: target company not mentioned; "
            f"{stale} outside the {state.request.lookback_days}-day window; "
            f"{unattributed} news item(s) whose event is about another company)",
            {
                "candidates": [
                    {"type": c.signal_type.value, "score": round(c.raw_score, 3),
                     "corroboration": c.corroboration_count, "patterns": c.matched_patterns[:2]}
                    for c in final_candidates
                ],
                "off_target": off_target, "stale": stale, "unattributed": unattributed,
                "syndicated_duplicates": stories.duplicates,
                "unattributed_titles": unattributed_titles,
            }
        )

        return state
