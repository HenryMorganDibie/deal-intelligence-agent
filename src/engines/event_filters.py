"""
Is a market-wide event headline about a company?

The signal rules (deterministic_engine) are written for a company's own news, where the company is already
known. Applied to the whole market's headlines they also match politics and personal news: a fraud probe of a
congresswoman, police charges in a ministry fraud, a journalist's arrest, a woman fined for harassment. This
module keeps an event only when the headline is about a company: it names one (a listed company, a curated
company, a name with a corporate suffix, or a possessive like "Intels' bid"), or describes one ("a top bank",
"15 companies"), and is not dominated by political, police or personal subjects.

Standard library only: the Corporate of the Week script imports it outside the service.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

_LISTED_FILE = Path(__file__).resolve().parents[1] / "data" / "african_listed_companies.json"

# A company described rather than named.
_CORPORATE_NOUN = re.compile(
    r"(?i)\b(?:banks?|plc|ltd|limited|group|holdings?|compan(?:y|ies)|firms?|insurers?|telcos?|airlines?|fintechs?|"
    r"operators?|miners?|mining\s+compan\w+|brewer(?:y|ies)?|refiner(?:y|ies)|corporation|chains?|retailers?|lenders?|"
    r"startups?|manufacturers?|bottlers?|distributors?|conglomerates?|subsidiar(?:y|ies)|listed|shareholders?|"
    r"board\s+of\s+directors|ceo|cfo|chief\s+executive|managing\s+director|chairman|auditors?|microfinance|"
    r"listing|ipo|stock\s+exchange|profits?|revenues?|earnings|dividends?|results|guidance|output|sales|turnover|"
    r"profit\s+warning|directeur\s+g[ée]n[ée]ral|\bdg\b|pdg|conseil\s+d['’]administration|soci[ée]t[ée]|entreprise|"
    r"filiale|b[ée]n[ée]fice|chiffre\s+d['’]affaires|r[ée]sultats|[ée]mission\s+obligataire|actionnaires?)\b")
# A name that says it is a company ("Lafarge Africa Plc", "Access Holdings").
_SUFFIXED_NAME = re.compile(
    r"\b[A-Z][\w&.'’-]*(?:\s+[A-Z][\w&.'’-]*){0,3}\s+(?:Plc|PLC|Ltd|Limited|Holdings|Group|Bank|Insurance|Airways|"
    r"Telecom|Cement|Breweries|Petroleum|Energy|Mining|Resources|Industries|Motors|Foods|Capital)\b")
_HEADLINE_VERBS = {"revokes", "fines", "suspends", "sanctions", "orders", "approves", "acquires", "appoints", "sues",
                   "probes", "charges", "bans", "warns", "names", "picks", "backs", "buys", "sells", "fined", "hits",
                   "court", "regulator", "exclusive", "breaking", "update", "new", "why", "how", "after", "as"}
# "Intels' bid to restrain...", "Glo's licence": a possessive followed by something a company has.
_CORPORATE_POSSESSION = re.compile(
    r"\b(?P<name>[A-Z][\w&.-]{2,})(?:['’]s?|['’])\s+(?:bid|licen[cs]e|shares|shareholders|appeal|suit|petition|"
    r"application|operations|accounts|board|directors|subsidiary|customers|network|platform|plant|factory|mine)\b")
# Political, police, public-body and personal subjects.
_NON_CORPORATE = re.compile(
    r"(?i)\b(?:president(?:ial)?|senators?|congress(?:wo)?man|lawmakers?|ex-lawmaker|\bmps?\b|governors?|opposition|"
    r"treason|election|campaign|political|parliament(?:ary)?|immigration|citizenship|dna|marr(?:y|ied)|"
    r"protests?|protesters?|journalists?|activists?|police|policemen|headmaster|shs|pupils?|students?|"
    r"\b(?:man|woman|boy|girl|teen|son|daughter|wife|husband|sister|brother|widow)\b|public\s+protector|city\s+of|"
    r"municipalit(?:y|ies)|ministry\s+fraud|labou?r\s+ministry|ipoa|passengers|importers|motorists|traders\s+face|"
    r"water\s+theft|pitch\s+encroachment|npfl|\bfc\b|league|football|club|church|pastor|imam|celebrity|actress|"
    r"musician|pr[ée]sident(?:e)?\s+(?:du|de\s+la|des)\s+(?:mali|r[ée]publique|s[ée]nat|parti)|minist(?:er|re)s?\b|"
    r"d[ée]put[ée]s?|parti\b|party\b|apc\b|pdp\b|anc\b|militaires?|soldiers?|army|junta|coup)\b")
# People are named with a role: "Alakija, Billionaire Businesswoman", "Mr Emefiele".
_PERSON_CUE = re.compile(
    r"(?i)\b(?:billionaire|businessman|businesswoman|tycoon|mogul|mr|mrs|ms|dr|chief|senator|governor|minister|"
    r"ex-governor|former)\b")


# Ownership changes are checked by the deal extractor; "Africa's richest man acquires 25% of Kenya Pipeline"
# is a deal whatever its subject.
_TRANSACTION_TYPES = {"m_and_a_activity", "insider_activity"}


@lru_cache(maxsize=1)
def listed_names() -> frozenset[str]:
    """Listed African companies (the backtest universe) and the curated list, as headlines write them."""
    names: set[str] = set()
    try:
        names.update(json.loads(_LISTED_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    try:
        from src.data.african_companies import AFRICAN_COMPANIES
        names.update(AFRICAN_COMPANIES)
    except ImportError:
        pass
    # A one-word listed name that is also an ordinary word ("Equity", "Transcorp" is fine) is too loose to count.
    return frozenset(n for n in names if len(n) >= 3)


@lru_cache(maxsize=1)
def _listed_pattern() -> Optional[re.Pattern]:
    names = sorted(listed_names(), key=len, reverse=True)
    if not names:
        return None
    return re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(n) for n in names) + r")(?![\w-])")


def named_company(headline: str) -> Optional[str]:
    """The company a headline names, when it names one: a listed or curated company, a suffixed name, or a
    possessive like "Intels' bid" whose owner is not a person."""
    text = headline or ""
    listed = _listed_pattern()
    if listed and (m := listed.search(text)):
        return m.group(0)
    if m := _SUFFIXED_NAME.search(text):
        words = m.group(0).split()
        while len(words) > 1 and words[0].lower() in _HEADLINE_VERBS:
            words.pop(0)                                # "Sudan Revokes Abu Dhabi Islamic Bank" -> the bank
        return " ".join(words)
    m = _CORPORATE_POSSESSION.search(text)
    if m and not _PERSON_CUE.search(text):
        return m.group("name")
    return None


def is_corporate_event(headline: str, signal_type: Optional[str] = None) -> bool:
    """Whether a market-wide event headline is about a company (see the module docstring).

    A political or personal headline counts only when a listed company is its subject. Any other headline
    must name a company or describe one ("a top bank was fined", "profit warning")."""
    if signal_type in _TRANSACTION_TYPES:
        return True                                     # deal rules require transaction wording already
    text = headline or ""
    name = named_company(text)
    listed = _listed_pattern()
    names_listed = bool(listed and listed.search(text))
    political = bool(_NON_CORPORATE.search(text))
    if political:
        # A political or personal story counts only when a listed company is its subject ("Sanlam appoints..."),
        # not when it is mentioned ("man who posed as Sanlam broker fined").
        return bool(names_listed and listed and listed.match(text.lstrip("\"'‘“ ")))
    # Otherwise the headline must name a company or describe one; a fine, probe or loss with neither is a
    # public, personal or macroeconomic matter.
    return bool(name or _CORPORATE_NOUN.search(text))
