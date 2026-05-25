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
from typing import Optional

from src.schemas.models import (
    SECFiling, NewsItem, SignalCandidate, SignalType, AgentState
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

SIGNAL_RULES: list[tuple[SignalType, list[str], float]] = [

    # ── M&A Activity ──
    (SignalType.MA_ACTIVITY, [
        r"\bdefinitive\s+(merger|acquisition|agreement)\b",
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
        r"\bdebt\s+(maturity|covenant|restructur)\b",
        r"\bimpairment\s+(charge|loss|write[-\s]down)\b",
        r"\bgoodwill\s+impairment\b",
        r"\bcash\s+(burn|runway|shortage)\b",
    ], 0.78),
    (SignalType.CREDIT_RISK, [
        r"\b(credit\s+rating|leverage\s+ratio|debt[-\s]to[-\s]equity)\b",
        r"\bnet\s+debt\b.{0,30}\b(exceeded?|surpassed?|increased?)\b",
        r"\brefinanc(e|ing|ed)\b",
    ], 0.55),

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
        r"\b(liquidat(e|ion|or)|wind(ing)?\s+up|wound\s+up)\b",
        r"\bdebt\s+(moratorium|standstill|restructur)\b",
        r"\bcreditor\s+(protection|committee|arrangement)\b",
        r"\b(distressed|impaired)\s+(asset|portfolio|loan)\b",
    ], 0.80),
    (SignalType.DISTRESSED_ASSET, [
        r"\bnon[-\s]performing\s+(loan|asset|portfolio)\b",
        r"\bwrite[-\s]off\b",
        r"\basset\s+disposal\b.{0,30}\b(forced|compelled|required)\b",
    ], 0.60),

    # ── Earnings Surprise ──
    (SignalType.EARNINGS_SURPRISE, [
        r"\bprofit\s+warning\b",
        r"\brevenueor\s+earnings\s+(restatement|revision|correction)\b",
        r"\bheadline\s+earnings?\b.{0,30}\b(declin|fall|drop|miss|below)\b",
        r"\bguidance\s+(cut|lowered?|reduced?|withdrawn?)\b",
        r"\btrading\s+(update|statement)\b.{0,40}\b(below|miss|declin)\b",
        r"\bsignificantly\s+below\s+(expectations?|guidance|consensus)\b",
    ], 0.88),
    (SignalType.EARNINGS_SURPRISE, [
        r"\b(revenue|earnings|profit|ebitda)\b.{0,20}\b(miss|below|declin|fell|dropped)\b",
        r"\bloss\s+(after\s+tax|before\s+tax|per\s+share)\b",
        r"\bnegative\s+(surprise|result|performance)\b",
        r"\bbelow[-\s](plan|budget|forecast|expectations?)\b",
    ], 0.72),
    (SignalType.EARNINGS_SURPRISE, [
        r"\bweaker\s+(than\s+expected|results?|performance)\b",
        r"\bdisappointing\s+(results?|earnings?|revenue)\b",
    ], 0.55),

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
        r"\binterim\s+(ceo|cfo|md|chief\s+executive)",
        r"\bboard\s+(dissolution|reconstitution|restructure)\b",
    ], 0.75),
    (SignalType.LEADERSHIP_CHANGE, [
        r"\b(leadership|management)\s+(change|transition|succession)\b",
        r"\bsuccession\s+plan\b",
    ], 0.50),

    # ── Regulatory Action ──
    (SignalType.REGULATORY_ACTION, [
        r"\b(sec|fsca|cma|cbn|sarb|cbk)\b.{0,30}\b(invest(igat|ment)|probe|enforcement|sanction|fine|penalty|subpoena)\b",
        r"\b(doj|ftc|competition\s+commission)\b.{0,30}\b(invest|antitrust|charge|fine)\b",
        r"\blicen(c|s)e\s+(revoked?|suspended?|cancelled?)\b",
        r"\bconsent\s+(order|decree|agreement)\b.{0,30}\b(regulat|enforce|penalt)\b",
        r"\bcriminal\s+(charge|referral|indictment)\b.{0,30}\b(fraud|financ|securi)\b",
    ], 0.93),
    (SignalType.REGULATORY_ACTION, [
        r"\bregulatory\s+(action|enforcement|sanction|inquiry|investigation)\b",
        r"\b(fraud|misconduct|manipulation)\s+(alleg|invest|probe|charge)\b",
        r"\bnon[-\s]compliance\b.{0,30}\b(regulat|penalt|fine)\b",
        r"\bshow[-\s]cause\s+(notice|letter|order)\b",
        r"\b(market|financial)\s+(misconduct|manipulation|abuse)\b",
    ], 0.80),
    (SignalType.REGULATORY_ACTION, [
        r"\b(regulatory|compliance)\s+(concern|issue|breach|violation)\b",
        r"\bwarning\s+letter\b.{0,30}\b(regulat|author|govern)\b",
    ], 0.58),

    # ── Debt Restructuring ──
    (SignalType.DEBT_RESTRUCTURE, [
        r"\bdebt\s+(restructur(ing|ed?)|renegotiat|relief|forgiven)\b",
        r"\bhaircut\b.{0,20}\b(debt|bond|creditor|lender)\b",
        r"\bprincipal\s+(reduction|write[-\s]down|forgiven)\b",
        r"\bextension\s+of\s+(maturity|repayment|loan\s+term)\b",
        r"\bforbearance\s+(agreement|period|granted)\b",
    ], 0.88),
    (SignalType.DEBT_RESTRUCTURE, [
        r"\b(bond|loan|facility)\s+(restructur|amendment|modification|waiver)\b",
        r"\bcreditor\s+(negotiation|settlement|agreement)\b",
        r"\bdeferred\s+(payment|repayment|interest)\b",
        r"\bdebt[-\s](for[-\s]equity|swap)\b",
    ], 0.75),
    (SignalType.DEBT_RESTRUCTURE, [
        r"\brefinanc(ing|ed?)\b.{0,20}\b(debt|facility|bond)\b",
        r"\bmaturity\s+(extension|profile|wall)\b",
    ], 0.55),

    # ── Insider Activity ──
    (SignalType.INSIDER_ACTIVITY, [
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
        r"\bproposed\s+(board|director)\s+nominee\b.{0,30}\b(activist|investor)\b",
    ], 0.72),
    (SignalType.INSIDER_ACTIVITY, [
        r"\bopen[-\s]market\s+(purchase|sale)\b",
        r"\bsignificant\s+beneficial\s+(owner|holding)\b",
    ], 0.52),
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


def _match_rules(text: str) -> list[tuple[SignalType, list[str], float]]:
    """
    Run all signal rules against text.
    Returns list of (signal_type, matched_patterns, base_score) for each hit.
    Takes the highest-scoring rule per signal type.
    """
    text_lower = text.lower()
    best: dict[SignalType, tuple[list[str], float]] = {}

    for signal_type, patterns, base_score in SIGNAL_RULES:
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


def _source_credibility(source_name: str) -> float:
    """Look up credibility score for a source."""
    for key, score in SOURCE_CREDIBILITY.items():
        if key.lower() in source_name.lower():
            return score
    return DEFAULT_CREDIBILITY


class DeterministicSignalEngine:
    """
    Phase 2: Deterministic signal detection.
    Runs before ANY LLM call. Produces SignalCandidate objects
    from pure pattern matching + NER. No ML. No LLM. Fully reproducible.
    """

    def run(self, state: AgentState) -> AgentState:
        state.log("deterministic_engine", "Running deterministic signal engine")

        candidates: list[SignalCandidate] = []

        # Process filings
        for filing in state.filings:
            text = " ".join(filter(None, [
                filing.description,
                filing.raw_excerpt,
                filing.form_type,
            ]))
            if not text.strip():
                continue
            hits = _match_rules(text)
            credibility = _source_credibility(filing.form_type)  # filing type is the source signal here
            # SEC / exchange filings get top credibility
            if filing.cik in ("NGX", "JSE", "NSE-KE"):
                credibility = 0.95
            elif filing.form_type in ("8-K", "JSE SENS", "NGX Announcement", "NSE Kenya Disclosure"):
                credibility = 1.00

            for sig_type, matched_patterns, base_score in hits:
                raw_score = min(base_score * credibility, 1.0)
                candidates.append(SignalCandidate(
                    signal_type=sig_type,
                    matched_patterns=matched_patterns,
                    source_text=text[:500],
                    source_url=filing.document_url,
                    source_type="filing",
                    source_name=filing.form_type,
                    filing_reference=filing.accession_number,
                    entity_mentions=_extract_entities(text),
                    corroboration_count=1,
                    raw_score=raw_score,
                ))

        # Process news items
        for news in state.news_items:
            text = f"{news.title} {news.snippet}"
            hits = _match_rules(text)
            credibility = _source_credibility(news.source)

            for sig_type, matched_patterns, base_score in hits:
                raw_score = min(base_score * credibility * news.relevance_score, 1.0)
                if raw_score < 0.20:
                    continue  # filter very weak news hits
                candidates.append(SignalCandidate(
                    signal_type=sig_type,
                    matched_patterns=matched_patterns,
                    source_text=text[:500],
                    source_url=news.url,
                    source_type="news",
                    source_name=news.source,
                    entity_mentions=_extract_entities(text),
                    corroboration_count=1,
                    raw_score=raw_score,
                ))

        # ── Corroboration counting ───────────────────────────────────────
        # Group candidates by signal_type. Count unique source_types confirming.
        # Merge into one candidate per signal_type, keeping highest raw_score.
        merged: dict[SignalType, SignalCandidate] = {}
        corroboration_tracker: dict[SignalType, set[str]] = {}

        for c in candidates:
            if c.signal_type not in merged:
                merged[c.signal_type] = c
                corroboration_tracker[c.signal_type] = {c.source_type + ":" + c.source_name}
            else:
                corroboration_tracker[c.signal_type].add(c.source_type + ":" + c.source_name)
                # Take higher raw_score, merge patterns
                existing = merged[c.signal_type]
                merged_patterns = list(dict.fromkeys(existing.matched_patterns + c.matched_patterns))
                if c.raw_score > existing.raw_score:
                    merged[c.signal_type] = c.model_copy(update={
                        "matched_patterns": merged_patterns,
                        "corroboration_count": len(corroboration_tracker[c.signal_type]),
                    })
                else:
                    merged[c.signal_type] = existing.model_copy(update={
                        "matched_patterns": merged_patterns,
                        "corroboration_count": len(corroboration_tracker[c.signal_type]),
                    })

        # Update corroboration counts
        final_candidates = []
        for sig_type, candidate in merged.items():
            final_candidates.append(candidate.model_copy(update={
                "corroboration_count": len(corroboration_tracker[sig_type])
            }))

        # Sort by raw_score descending
        final_candidates.sort(key=lambda c: c.raw_score, reverse=True)
        state.signal_candidates = final_candidates

        state.log(
            "deterministic_engine",
            f"Engine produced {len(final_candidates)} signal candidates",
            {
                "candidates": [
                    {"type": c.signal_type.value, "score": round(c.raw_score, 3),
                     "corroboration": c.corroboration_count, "patterns": c.matched_patterns[:2]}
                    for c in final_candidates
                ]
            }
        )

        return state
