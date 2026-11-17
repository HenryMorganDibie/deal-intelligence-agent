"""
Investment opportunities: governments, state companies and firms in Africa looking for investors or partners.

These are solicitations, not transactions, so they are sourced and stored apart from deals and never count in deal
totals. A headline is an opportunity only when all of these hold:
  * it solicits: a party seeks, woos or courts investors, partners or funding, or opens assets or a bid round to
    investors;
  * the object is specific: a project, an asset, a sector or a bid round ("for a $26bn gas pipeline", "to build AI
    data centres"), not just a place or an event ("woos investors to Ghana at a summit");
  * it is placed in an African country;
  * it does not report a completed deal (raises, secures, acquires) or a call for more investment in general.
Reports of one opportunity by several outlets are combined into one record with every source.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Iterable, Optional
from urllib.parse import quote

import httpx

from src.data.africa_countries import COUNTRIES, countries_in_text
from src.engines import deals as deals_mod

_ADJ = r"(?:fresh|new|foreign|private|local|international|strategic|global|more|potential|equity|technical|credible)"
_SOLICIT = re.compile(
    rf"(?i)\b(?P<verb>seeks?|seeking|woos?|wooing|courts?|courting|invites?|inviting|scouts?\s+for|hunts?\s+for|"
    rf"looks?\s+for|looking\s+for|targets?)\s+(?:{_ADJ}\s+){{0,3}}"
    rf"(?P<obj>investors?|partners?|partnerships?|investments?|funding|financing|capital|bidders?|financiers?)\b")
_OPENS = re.compile(
    r"(?i)\b(?:opens?|offers?|puts?|launch(?:es)?|unveils?)\b.{0,70}?\b(?:to\s+(?:private|international|foreign|local)?"
    r"\s*(?:investment|investors|bidders)|for\s+(?:sale|bids?|bidding|concession|investment|privati[sz]ation)|"
    r"bid\s+round|licensing\s+round|bid\s+portal)\b")
_BID_ROUND = re.compile(r"(?i)\b(?:bid|licensing)\s+(?:round|portal)\b|\binvites?\s+bids\b|\bexpressions?\s+of\s+interest\b")
_FRENCH = re.compile(r"(?i)\b(?:cherche|recherche|appelle)\s+(?:des\s+|de\s+nouveaux\s+)?"
                     r"(?P<obj>investisseurs|partenaires|financements?)\b")

# What the money or partner is for: a project, an asset, a sector, or a bid round.
_SPECIFIC = re.compile(
    r"(?i)\b(?:projects?|pipelines?|refiner(?:y|ies)|ports?|seaports?|terminals?|rail(?:way)?s?|standard\s+gauge|"
    r"roads?|highways?|bridges?|airports?|solar|wind|hydro(?:power)?|geothermal|power|electricity|energy|grid|"
    r"plants?|factor(?:y|ies)|facilit(?:y|ies)|mines?|mining|minerals?|lithium|copper|gold|bauxite|alumina|"
    r"oil|gas|lng|blocks?|fields?|data\s+cent(?:re|er)s?|hubs?|zones?|parks?|estates?|housing|hospitals?|"
    r"agro|agricultur\w*|farms?|coffee|cocoa|cotton|fish(?:eries)?|catfish|processing|manufacturing|"
    r"tourism|hotels?|stakes?|shares?|concessions?|privati[sz]\w+|assets?|transport|logistics|water|"
    r"telecoms?|fibre|fiber|satellites?|startups?|"
    r"bid\s+round|bid\s+portal|licensing\s+round|sector|industry|value\s+chain)\b")
# Calls for investment in general, policy talk and court cases are not opportunities.
_GENERAL = re.compile(
    r"(?i)\b(?:more|greater|increased|additional|sustained)\s+(?:investment|funding|investors)\b|\bcalls?\s+for\b|"
    r"\binvestment\s+climate\b|\bconducive\b|\benabling\s+environment\b|\bban\b|\bbans\b|\bsupport\s+to\s+fight\b|"
    r"\bhate\s+speech\b|\bmisinformation\b|\bcampaign\s+against\b|\bvictims\b|\belection")
_COMPLETED = re.compile(
    r"(?i)\b(?:raises?|raised|secures?|secured|closes?|closed|acquires?|acquired|completes?|completed|bags?|lands?|"
    r"signs?|signed|inks?|injects?|invested|commits?|committed|backs|backed|wins?|won|approves?|approved|"
    r"lawsuit|injunction|ruling|ruled)\b")
# Names the country matcher leaves out as ambiguous: a bare "Congo" in business news is the DRC.
_ALIASES = ((re.compile(r"(?i)\bcongo[- ]brazzaville\b|\brepublic\s+of\s+(?:the\s+)?congo\b"), "CG"),
            (re.compile(r"(?i)\bDRC\b|\bcongo\b"), "CD"))
_PREFIX = re.compile(r"^\s*(?:[A-Z][\w-]*_[\w-]*|breaking|exclusive|update|video|watch|opinion|analysis)\s*[:\-|]\s*", re.I)

_STATUS = {"investor": "Seeking investors", "investment": "Seeking investors", "capital": "Seeking investors",
           "partner": "Seeking partners", "partnership": "Seeking partners", "funding": "Seeking funding",
           "financing": "Seeking funding", "financier": "Seeking funding", "bidder": "Open for bids",
           "investisseur": "Seeking investors", "partenaire": "Seeking partners", "financement": "Seeking funding"}

STOP = {"seeks", "seeking", "investors", "investor", "partners", "partner", "funding", "investment", "woos", "courts",
        "invites", "with", "from", "into", "over", "under", "after", "this", "that", "their", "fresh", "foreign", "new",
        "private", "international", "strategic", "billion", "million", "says", "said", "plans", "minister", "government",
        "state", "federal", "national", "african", "africa"}


def clean_title(title: str) -> str:
    t = _PREFIX.sub("", (title or "").strip())
    return re.sub(r"\s*(?:\s-\s|\|)\s*[^-|]{2,60}$", "", t).strip()   # " - Publisher" and "| Publisher" tails


def _soliciting_party(title: str, start: int) -> Optional[str]:
    """The party before the solicitation verb, from its own clause: "Lekki port hits capacity as NPA seeks ..." ->
    "NPA"; "Ghana's PHDC ..." keeps the possessive."""
    head = title[:start].strip(" ,:;-–")
    for sep in (" as ", " while ", ", ", "; ", ": ", " – ", " - "):
        if sep == ", " and len(head.split()) <= 4:
            continue                                    # "Nigeria, UK seek ...": a list of parties, kept whole
        if sep in head:
            head = head.rsplit(sep, 1)[1]
    head = re.sub(r"(?i)^(?:the|president|governor|minister|gov\.?|dr\.?)\s+", "", head).strip()
    words = head.split()
    if not words or len(words) > 7 or not words[0][:1].isupper():
        return None
    return head


def _object_phrase(title: str, end: int) -> str:
    """What follows the solicitation: "for $26B Gas Pipeline to Morocco and Europe"."""
    tail = title[end:]
    return re.split(r"(?i)\s+(?:at|amid|during|as|after|ahead\s+of|on\s+sidelines)\s+|[,;|]", tail, maxsplit=1)[0].strip()


def extract(item: dict) -> Optional[dict]:
    """An opportunity record from one news item, or None."""
    title = clean_title(item.get("title") or "")
    if not title or _COMPLETED.search(title) or _GENERAL.search(title):
        return None
    m = _SOLICIT.search(title) or _FRENCH.search(title)
    opened = None if m else (_OPENS.search(title) or _BID_ROUND.search(title))
    if not m and not opened:
        return None
    if m:
        obj = (m.groupdict().get("obj") or "").lower()
        status = next((v for k, v in _STATUS.items() if obj.startswith(k)), "Seeking investors")
        what = _object_phrase(title, m.end())
        if not _SPECIFIC.search(what):
            return None                                 # "woos investors to Ghana", "seeks funding for a campaign"
        party = _soliciting_party(title, m.start())
    else:
        status, what = "Open for bids", title
        party = _soliciting_party(title, opened.start())
    text = f"{title} {item.get('snippet') or ''}"
    found = [c.iso2 for c in countries_in_text(title)] or [c.iso2 for c in countries_in_text(text)]
    if not found:
        found = next(([iso] for rx, iso in _ALIASES if rx.search(text)), [])
    # The country edition a search ran in places a story only when it names no country and is not pan-African
    # ("Edo seeks private investment ..." from Nigeria's edition), never one about Africa at large.
    hint = item.get("country_hint")
    if not found and hint and not re.search(r"(?i)\bafrica", text):
        found = [hint]
    countries = list(dict.fromkeys(found))
    if hint in countries:                               # of the countries named, the search edition's leads
        countries.remove(hint)
        countries.insert(0, hint)
    if not countries:
        return None                                     # not placed in Africa
    day = (item.get("date") or "")[:10] or None
    year = int(day[:4]) if day and day[:4].isdigit() else None
    sought = deals_mod.deal_amount(title)
    record = {
        "record_type": "investment_opportunity", "deal_type": "investment_opportunity", "stage": "proposed",
        "headline": title, "opportunity_title": title, "opportunity_status": status,
        "soliciting_party": party, "target": (what[:120] or title[:120]).strip(),
        "country": countries[0], "countries": countries, "sector": deals_mod.classify_sector(title),
        "announced": day, "amount": None, "amount_usd": None,
        "amount_sought": sought[0] if sought else None, "amount_sought_currency": sought[1] if sought else None,
        "amount_sought_usd": deals_mod.to_usd(sought[0], sought[1], year) if sought else None,
        "investors": [], "commitment_confirmed": False,
        "commitment_note": "No investment commitment or completed transaction is confirmed by the source.",
        "sources": [{"url": item.get("url"), "publisher": item.get("publisher") or None, "date": day,
                     "title": item.get("title"), "stage": "announced"}],
    }
    record["id"] = opportunity_id(record)
    return record


def _tokens(record: dict) -> set[str]:
    words = re.findall(r"[a-z0-9$]+", (record.get("headline") or "").lower())
    return {w for w in words if len(w) >= 4 and w not in STOP and not w.isdigit()}


def same_opportunity(a: dict, b: dict) -> bool:
    """Two reports of one opportunity: a shared country, announced within 21 days, and at least two distinctive
    words in common ("gas", "pipeline", "morocco")."""
    if not set(a.get("countries") or []) & set(b.get("countries") or []):
        return False
    da, db = a.get("announced") or "", b.get("announced") or ""
    if da and db:
        from datetime import date
        if abs((date.fromisoformat(da) - date.fromisoformat(db)).days) > 21:
            return False
    return len(_tokens(a) & _tokens(b)) >= 2


def opportunity_id(record: dict) -> str:
    key = f"opp|{record.get('country')}|{(record.get('announced') or '')[:7]}|{record.get('headline', '').lower()}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def _combine(base: dict, other: dict) -> dict:
    urls = {s.get("url") for s in base.get("sources") or []}
    sources = list(base.get("sources") or []) + [s for s in other.get("sources") or [] if s.get("url") not in urls]
    out = {**base, "sources": sources}
    for key in ("soliciting_party", "sector", "amount_sought", "amount_sought_currency", "amount_sought_usd"):
        if not out.get(key) and other.get(key):
            out[key] = other[key]
    out["countries"] = list(dict.fromkeys([*(base.get("countries") or []), *(other.get("countries") or [])]))
    return out


def merge_into(new: Iterable[dict], existing: Iterable[dict]) -> list[dict]:
    """New opportunity reports combined with each other and with stored opportunities: records to write. A report
    of a stored opportunity adds its source to that record instead of creating another."""
    stored = [e for e in existing if deals_mod.is_investment_opportunity(e) and deals_mod.is_visible(e)]
    out: dict[str, dict] = {}
    for rec in sorted(new, key=lambda r: r.get("announced") or ""):
        twin = next((o for o in out.values() if same_opportunity(o, rec)), None) \
            or next((s for s in stored if same_opportunity(s, rec)), None)
        if twin:
            out[twin["id"]] = _combine(out.get(twin["id"], twin), rec)
        else:
            out[rec["id"]] = rec
    return list(out.values())


def extract_all(items: Iterable[dict]) -> list[dict]:
    return [r for r in (extract(it) for it in items) if r]


# ── Sourcing ──────────────────────────────────────────────────────────────────────────────────────────────────

PAN_AFRICAN = ('"seeks investors" Africa', '"woos investors" Africa', '"courts investors" Africa',
               '"seeks partners" Africa project', '"seeks funding" Africa project', '"invites investors" Africa',
               '"opens" "to private investment" Africa', '"bid round" Africa oil gas blocks',
               '"strategic investor" Africa stake sale', '"expression of interest" Africa project investors')
COUNTRY_TERMS = '("seeks investors" OR "woos investors" OR "courts investors" OR "seeks partners" OR "invites investors" OR "private investment")'
FRENCH_TERMS = '("cherche des investisseurs" OR "recherche des partenaires" OR "appel à investisseurs")'


def queries(window: str = "when:7d") -> list[tuple[str, str, Optional[str]]]:
    """(url, label, country) Google News searches for solicitations: pan-African, then every country's edition."""
    out = [(f"https://news.google.com/rss/search?q={quote(q + ' ' + window)}&hl=en-GB&gl=GB&ceid=GB:en",
            f"opportunities: {q}", None) for q in PAN_AFRICAN]
    for c in COUNTRIES:
        name = f'"{c.name}"' if " " in c.name else c.name
        if "en" in c.languages:
            out.append((c.news_url(f"{name} {COUNTRY_TERMS} {window}", "en"), f"{c.name} opportunities", c.iso2))
        if "fr" in c.languages:
            from src.engines.market_feed import localized_country_name
            fr = localized_country_name(c, "fr")
            fr = f'"{fr}"' if " " in fr else fr
            out.append((c.news_url(f"{fr} {FRENCH_TERMS} {window}", "fr"), f"{c.name} opportunités", c.iso2))
    return out


async def collect(window: str = "when:7d", concurrency: int = 10, timeout: float = 20) -> list[dict]:
    """News items from the solicitation searches, each labelled with the country searched."""
    from src.engines.market_feed import parse_feed
    sem = asyncio.Semaphore(concurrency)
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) deal-intelligence-agent/1.0"}

    async def one(client, url, label, iso2):
        async with sem:
            try:
                r = await client.get(url)
                r.raise_for_status()
            except httpx.HTTPError:
                return []
        items = parse_feed(r.text)
        for it in items:
            it.setdefault("country_hint", iso2)
        return items
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        batches = await asyncio.gather(*(one(client, u, label, c) for u, label, c in queries(window)))
    seen, out = set(), []
    for batch in batches:
        for it in batch:
            key = re.sub(r"\W+", " ", (it.get("title") or "").lower()).strip()
            if key and key not in seen:
                seen.add(key)
                out.append(it)
    return out
