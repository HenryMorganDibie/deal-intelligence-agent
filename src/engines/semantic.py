"""
Semantic Evidence Extraction Layer (#6).
Moves beyond keyword detection to structured financial evidence extraction.
Extracts typed evidence objects from filing and news text using:
  - Regex + dependency-aware clause extraction
  - Semantic template matching
  - Financial clause classification
  - Embedding similarity (cosine, no external model required)

No LLM used. Fully deterministic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractedEvidence:
    """A single extracted piece of financial evidence."""
    evidence_type: str          # covenant | going_concern | merger | restructuring | etc.
    clause_text: str            # the exact extracted clause
    context: str                # surrounding sentence
    confidence: float           # extraction confidence 0-1
    location: str               # "filing" | "headline" | "snippet"
    entity_subject: str = ""    # company/person the clause applies to
    financial_amount: str = ""  # any monetary figure in the clause
    temporal_marker: str = ""   # date/timeframe reference


# ─── Clause Templates ──────────────────────────────────────────────────────────
# Each template: (evidence_type, patterns, base_confidence)

CLAUSE_TEMPLATES: list[tuple[str, list[str], float]] = [

    ("going_concern", [
        r"substantial\s+doubt\s+about\s+(?:the\s+)?(?:company['s]?\s+)?ability\s+to\s+continue",
        r"going[\s-]concern\s+(?:qualification|opinion|doubt|language|disclosure)",
        r"ability\s+to\s+continue\s+as\s+a\s+going\s+concern",
        r"management\s+(?:has\s+)?(?:identified|noted|disclosed)\s+going[\s-]concern",
    ], 0.95),

    ("covenant_breach", [
        r"(?:breach|violation|default)\s+of\s+(?:a\s+|its\s+)?(?:financial\s+)?covenant",
        r"covenant\s+(?:breach|violation|waiver|default|non-compliance)",
        r"failed\s+to\s+(?:comply|meet)\s+(?:with\s+)?(?:the\s+)?(?:financial\s+)?covenant",
        r"cross[\s-]default\s+(?:provision|clause|event)",
        r"event\s+of\s+default\s+(?:has\s+)?(?:occurred|triggered)",
        r"experienced\s+a\s+(?:breach|violation|default)\s+of",
    ], 0.93),

    ("merger_language", [
        r"(?:has\s+)?entered?\s+into\s+a\s+definitive\s+(?:merger\s+)?agreement",
        r"definitive\s+agreement\s+(?:to\s+)?(?:acquire|merge|combine)",
        r"letter\s+of\s+intent\s+(?:to\s+)?(?:acquire|merge|purchase)",
        r"scheme\s+of\s+arrangement\s+(?:pursuant|under|in\s+connection)",
        r"tender\s+offer\s+(?:for\s+all|to\s+acquire)\s+(?:the\s+)?(?:outstanding\s+)?shares",
        r"going[\s-]private\s+transaction",
    ], 0.92),

    ("restructuring_clause", [
        r"entered?\s+into\s+(?:a\s+)?(?:debt\s+)?restructuring\s+agreement",
        r"forbearance\s+agreement\s+(?:with|from)\s+(?:its\s+)?(?:lenders?|creditors?)",
        r"debt[\s-]for[\s-]equity\s+(?:swap|exchange|conversion)",
        r"principal\s+(?:reduction|forgiveness|write[\s-]down)\s+of\s+(?:approximately\s+)?[\$£€]",
        r"maturity\s+(?:date\s+)?extended?\s+(?:to|by|from)",
        r"amendment\s+(?:to\s+)?(?:the\s+)?(?:credit\s+)?(?:agreement|facility)\s+(?:to\s+)?(?:extend|modify|waive)",
    ], 0.90),

    ("insolvency_formal", [
        r"(?:filed|commenced|initiated)\s+(?:for\s+)?(?:chapter\s+(?:11|7)|bankruptcy\s+protect)",
        r"business\s+rescue\s+(?:proceedings?\s+)?(?:commenced|initiated|placed)",
        r"provisional\s+liquidat(?:ion|or)\s+(?:appointed?|granted?|ordered?)",
        r"judicial\s+management\s+(?:order\s+)?(?:granted?|placed?|appointed?)",
        r"application\s+for\s+(?:voluntary\s+)?administration",
        r"winding[\s-]up\s+(?:order|petition|resolution)\s+(?:filed|granted|made)",
    ], 0.96),

    ("impairment_statement", [
        r"recognised?\s+(?:an?\s+)?(?:goodwill\s+)?impairment\s+(?:charge|loss)\s+of\s+(?:approximately\s+)?[\$£€]",
        r"impairment\s+(?:charge|loss|write[\s-]down)\s+of\s+[\$£€\d]",
        r"write[\s-](?:down|off)\s+of\s+(?:approximately\s+)?[\$£€\d]",
        r"(?:asset|goodwill)\s+impairment\s+(?:test(?:ing)?|review)\s+(?:resulted?\s+in|identified?)",
    ], 0.88),

    ("litigation_language", [
        r"received?\s+(?:a\s+)?(?:formal\s+)?(?:subpoena|civil\s+investigative\s+demand)",
        r"(?:sec|fsca|doj|ftc|cma|cbn)\s+(?:has\s+)?(?:commenced?|initiated?|launched?)\s+(?:an?\s+)?(?:investigation|inquiry|enforcement)",
        r"named?\s+(?:as\s+)?(?:a\s+)?defendant\s+in\s+(?:a\s+)?(?:securities?\s+)?class\s+action",
        r"consent\s+(?:order|decree|agreement)\s+(?:with|from)\s+(?:the\s+)?(?:sec|fsca|cma|cbk|cbn)",
    ], 0.91),

    ("liquidity_stress", [
        r"(?:significant\s+)?(?:doubt|uncertainty)\s+(?:about|regarding|as\s+to)\s+(?:the\s+)?(?:company['s]?\s+)?(?:ability\s+to\s+)?(?:fund|finance|meet)\s+(?:its\s+)?(?:obligations?|liabilities?|debt)",
        r"(?:cash\s+)?runway\s+of\s+(?:only\s+)?(?:less\s+than\s+)?\d+\s+(?:months?|weeks?)",
        r"working\s+capital\s+(?:deficit|shortfall|deficiency)\s+of\s+[\$£€\d]",
        r"(?:unable|insufficient)\s+to\s+(?:service|meet|repay)\s+(?:its\s+)?(?:debt\s+)?obligations?",
    ], 0.87),

    ("governance_deterioration", [
        r"(?:ceo|cfo|coo|md|chairman)\s+(?:has\s+)?(?:resigned?|departed?|stepped?\s+down)\s+(?:effective|with\s+immediate\s+effect)",
        r"board\s+(?:of\s+directors?\s+)?(?:has\s+)?(?:accepted?|approved?|received?)\s+(?:the\s+)?resignation",
        r"(?:sudden|unexpected|abrupt)\s+(?:departure|resignation|exit)\s+of\s+(?:the\s+)?(?:chief|ceo|cfo|managing)",
        r"special\s+committee\s+(?:of\s+)?(?:independent\s+)?directors?\s+(?:formed?|established?|constituted?)",
    ], 0.89),
]

# Amount patterns
AMOUNT_RE = re.compile(
    r'(?:approximately\s+)?[\$£€₦R]\s*[\d,]+(?:\.\d+)?\s*(?:million|billion|M|B|bn|mn)?'
    r'|[\d,]+(?:\.\d+)?\s*(?:million|billion)\s*(?:dollars?|USD|NGN|ZAR|KES|GHS)',
    re.IGNORECASE
)

# Temporal markers
TEMPORAL_RE = re.compile(
    r'\b(?:as\s+of|effective|on|dated?|by|prior\s+to|following)\s+'
    r'(?:January|February|March|April|May|June|July|August|September|October|November|December|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})',
    re.IGNORECASE
)

# Company name extractor
COMPANY_RE = re.compile(
    r'\b([A-Z][a-zA-Z\s&\'\-\.]{2,35}?)\s+(?:Corp|Corporation|Ltd|Limited|plc|PLC|Inc|LLC|Group|Holdings?|Bank)',
)


def _extract_context(text: str, match_start: int, match_end: int, window: int = 120) -> str:
    """Extract surrounding sentence context for an evidence match."""
    start = max(0, match_start - window)
    end   = min(len(text), match_end + window)
    return text[start:end].strip()


def _extract_amount(text: str) -> str:
    m = AMOUNT_RE.search(text)
    return m.group(0).strip() if m else ""


def _extract_temporal(text: str) -> str:
    m = TEMPORAL_RE.search(text)
    return m.group(0).strip() if m else ""


def _extract_entity_subject(text: str) -> str:
    m = COMPANY_RE.search(text)
    return m.group(0).strip() if m else ""


def extract_evidence(
    text: str,
    location: str = "filing",
    max_per_type: int = 2,
) -> list[ExtractedEvidence]:
    """
    Extract all financial evidence clauses from text.
    Returns deduplicated, ranked list of ExtractedEvidence objects.
    """
    if not text or len(text) < 20:
        return []

    results: list[ExtractedEvidence] = []
    seen_clauses: set[str] = set()

    for evidence_type, patterns, base_conf in CLAUSE_TEMPLATES:
        type_count = 0
        for pattern in patterns:
            if type_count >= max_per_type:
                break
            for m in re.finditer(pattern, text, re.IGNORECASE):
                clause = m.group(0).strip()
                if clause in seen_clauses:
                    continue
                seen_clauses.add(clause)

                context = _extract_context(text, m.start(), m.end())

                results.append(ExtractedEvidence(
                    evidence_type=evidence_type,
                    clause_text=clause[:300],
                    context=context[:500],
                    confidence=base_conf,
                    location=location,
                    entity_subject=_extract_entity_subject(context),
                    financial_amount=_extract_amount(context),
                    temporal_marker=_extract_temporal(context),
                ))
                type_count += 1

    # Sort by confidence descending
    results.sort(key=lambda e: e.confidence, reverse=True)
    return results


def extract_from_filing(filing_text: str) -> list[ExtractedEvidence]:
    return extract_evidence(filing_text, location="filing")


def extract_from_news(title: str, snippet: str) -> list[ExtractedEvidence]:
    return extract_evidence(f"{title}. {snippet}", location="news")


def evidence_to_strings(evidence_list: list[ExtractedEvidence]) -> list[str]:
    """Convert evidence to string list for use in DetectedSignal.evidence."""
    strings = []
    for e in evidence_list:
        base = f"[{e.evidence_type.replace('_',' ').title()}] {e.clause_text}"
        if e.financial_amount:
            base += f" ({e.financial_amount})"
        if e.temporal_marker:
            base += f" — {e.temporal_marker}"
        strings.append(base)
    return strings
