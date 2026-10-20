"""
Investors, funds, LPs and GP activity, built from the deals database.

Every party in a deal gets a role:
  investor   equity investor in a funding round (lead or participant)
  lender     provider of a loan, facility or bond
  acquirer   buyer in an acquisition or merger
  seller     seller in an exit or divestment
  lp         limited partner / anchor commitment to a fund
  gp         fund manager raising or closing a fund

A profile aggregates one party's deals: counts by role, disclosed US dollars,
sectors, countries, stages, co-investors and the most recent transactions.
A curated registry of Africa-focused investors supplies type, headquarters and
name variants ("BII" and "CDC Group" are British International Investment), so
reports under different names land on one profile.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional

from src.engines.deals import normalise_name


@dataclass(frozen=True)
class Investor:
    name: str
    kind: str                  # dfi, multilateral, private_equity, venture_capital, growth, sovereign, pension, bank, accelerator
    hq: str
    aliases: tuple[str, ...] = ()


REGISTRY: tuple[Investor, ...] = (
    # Development finance institutions and multilaterals
    Investor("International Finance Corporation", "dfi", "Washington, DC, United States", ("IFC",)),
    Investor("British International Investment", "dfi", "London, United Kingdom", ("BII", "CDC Group", "CDC")),
    Investor("Proparco", "dfi", "Paris, France"),
    Investor("FMO", "dfi", "The Hague, Netherlands", ("Dutch entrepreneurial development bank",)),
    Investor("Norfund", "dfi", "Oslo, Norway"),
    Investor("Swedfund", "dfi", "Stockholm, Sweden"),
    Investor("Finnfund", "dfi", "Helsinki, Finland"),
    Investor("DEG", "dfi", "Cologne, Germany", ("DEG - Deutsche Investitions- und Entwicklungsgesellschaft",)),
    Investor("U.S. International Development Finance Corporation", "dfi", "Washington, DC, United States", ("DFC",)),
    Investor("European Investment Bank", "multilateral", "Luxembourg", ("EIB",)),
    Investor("African Development Bank", "multilateral", "Abidjan, Côte d'Ivoire", ("AfDB", "BAD", "Banque africaine de développement")),
    Investor("Afreximbank", "multilateral", "Cairo, Egypt", ("African Export-Import Bank",)),
    Investor("Africa Finance Corporation", "multilateral", "Lagos, Nigeria", ("AFC",)),
    Investor("Africa50", "multilateral", "Casablanca, Morocco"),
    Investor("Shelter Afrique", "multilateral", "Nairobi, Kenya"),
    Investor("Trade and Development Bank", "multilateral", "Nairobi, Kenya", ("TDB Group", "TDB")),
    Investor("Islamic Development Bank", "multilateral", "Jeddah, Saudi Arabia", ("IsDB",)),
    # Private equity and growth
    Investor("Helios Investment Partners", "private_equity", "London, United Kingdom", ("Helios",)),
    Investor("Development Partners International", "private_equity", "London, United Kingdom", ("DPI",)),
    Investor("Actis", "private_equity", "London, United Kingdom"),
    Investor("AfricInvest", "private_equity", "Tunis, Tunisia"),
    Investor("Adenia Partners", "private_equity", "Port Louis, Mauritius", ("Adenia",)),
    Investor("Amethis", "private_equity", "Paris, France"),
    Investor("Lightrock", "growth", "London, United Kingdom"),
    Investor("Ninety One", "private_equity", "London, United Kingdom"),
    Investor("Old Mutual Alternative Investments", "private_equity", "Cape Town, South Africa", ("OMAI",)),
    # Venture capital and accelerators
    Investor("Partech Africa", "venture_capital", "Paris, France", ("Partech",)),
    Investor("TLcom Capital", "venture_capital", "London, United Kingdom", ("TLcom",)),
    Investor("Novastar Ventures", "venture_capital", "Nairobi, Kenya", ("Novastar",)),
    Investor("4DX Ventures", "venture_capital", "Washington, DC, United States"),
    Investor("Ventures Platform", "venture_capital", "Abuja, Nigeria"),
    Investor("Future Africa", "venture_capital", "Lagos, Nigeria"),
    Investor("Norrsken22", "venture_capital", "Stockholm, Sweden"),
    Investor("Algebra Ventures", "venture_capital", "Cairo, Egypt"),
    Investor("Sawari Ventures", "venture_capital", "Cairo, Egypt"),
    Investor("Janngo Capital", "venture_capital", "Abidjan, Côte d'Ivoire", ("Janngo",)),
    Investor("Y Combinator", "accelerator", "San Francisco, United States", ("YC",)),
    # Sovereign and pension
    Investor("Public Investment Corporation", "pension", "Pretoria, South Africa", ("PIC",)),
    Investor("Nigeria Sovereign Investment Authority", "sovereign", "Abuja, Nigeria", ("NSIA",)),
    Investor("Fonds Mohammed VI pour l'Investissement", "sovereign", "Rabat, Morocco", ("Fonds Mohammed VI",)),
    Investor("Mubadala", "sovereign", "Abu Dhabi, United Arab Emirates", ("Mubadala Investment Company",)),
)

_ALIAS: dict[str, Investor] = {}
for _inv in REGISTRY:
    for _n in (_inv.name, *_inv.aliases):
        _ALIAS[normalise_name(_n)] = _inv


_ACRONYMS: dict[str, Investor] = {a: inv for inv in REGISTRY for a in inv.aliases
                                   if a.isupper() and len(a) >= 3 and a not in ("BID", "CDC")}


def canonical(name: Optional[str]) -> Optional[str]:
    """Registry name for a known investor, or the name as given."""
    if not name:
        return None
    key = normalise_name(name)
    if key in _ALIAS:
        return _ALIAS[key].name
    # "World Bank's IFC": an upper-case registry acronym as a whole word (case-sensitive, so "bid" is not IsDB).
    for word in re.findall(r"[A-Za-z0-9]+", name):
        if word in _ACRONYMS:
            return _ACRONYMS[word].name
    # Multi-word registry names inside a longer name ("Helios Investment Partners Fund IV" -> Helios).
    for alias, inv in _ALIAS.items():
        if " " in alias and f" {alias} " in f" {key} ":
            return inv.name
    # A descriptor before a registry name: "French DFI Proparco", "Dutch lender FMO".
    words = name.strip().split()
    for k in (1, 2):
        tail = normalise_name(" ".join(words[-k:])) if len(words) > k else ""
        if tail in _ALIAS and len(tail) >= 4:
            return _ALIAS[tail].name
    # Unknown parties: one display form per company ("Standard Bank Group" and "Standard Bank" are one,
    # "NATCO Pharma" and "Natco Pharma" are one). A lone remaining word is kept only if distinctive.
    stripped = re.sub(r"(?:\s+(?:Group|Holdings?|Plc|PLC|Limited|Ltd\.?|Inc\.?|S\.?A\.?))+$", "", name.strip())
    if len(stripped.split()) < 2 and (not stripped or stripped.lower() in _COMMON_WORDS or len(stripped) < 4):
        stripped = name.strip()
    return _DISPLAY.setdefault(normalise_name(stripped), stripped)


_DISPLAY: dict[str, str] = {}
_COMMON_WORDS = {"access", "equity", "standard", "first", "union", "national", "united", "sterling", "fidelity",
                 "heritage", "premier", "prime", "summit", "diamond", "royal", "liberty", "imperial", "capital",
                 "africa", "african", "global", "international"}

# Extraction fragments: a headline clause rather than a name ("Tolaram Welcomes IFC", "Why Uganda").
_FRAGMENT = re.compile(
    r"\b(welcomes?|makes?|confirms?|says?|plans?|eyes|backs?|announces?|secures?|raises?|signs?|seeks?|targets?|"
    r"invests?|wins?|gets?|bags?|joins?|launches?|unveils?|agreement|deal|move)\b|^(why|how|what|when|govt|others?|"
    r"other\s+investors|investors?|saudi\s+investor)\b|\.\s+\S",
    re.IGNORECASE,
)
_GENERIC_PARTY = re.compile(r"^(capital\s+market|investors?|others?|other\s+investors|govt|government|state|the\s+state)$",
                            re.IGNORECASE)


def split_names(name: Optional[str]) -> list[str]:
    """Canonical parties in an extracted party string: combined names are split ("IFC and Proparco" ->
    IFC, Proparco); headline fragments and generic phrases yield nothing, so no deal is credited to them."""
    if not name or not name.strip():
        return []
    raw = name.strip()
    parts = re.split(r"\s+(?:and|&|et|e)\s+|\s*,\s*", raw)
    if len(parts) > 1 and all(p.strip() for p in parts):
        # Split only when a part is a known investor: "Procter & Gamble" and "Johnson & Johnson" stay whole.
        if any(registry_entry(p) for p in parts):
            return [c for p in parts for c in split_names(p)]
    if _GENERIC_PARTY.match(raw) or normalise_name(raw) in _GENERIC_PARTY_KEYS or _FRAGMENT.search(raw):
        return []
    c = canonical(raw)
    return [c] if c else []


def registry_entry(name: str) -> Optional[Investor]:
    c = canonical(name)
    return _ALIAS.get(normalise_name(c)) if c else None


def parties(deal: dict) -> list[tuple[str, str]]:
    """(canonical name, role) for every party of a deal."""
    t = deal.get("deal_type")
    out: list[tuple[str, str]] = []

    def add(name: Optional[str], role: str) -> None:
        for c in split_names(name):
            if (c, role) not in out:
                out.append((c, role))

    if t == "equity_funding":
        add(deal.get("buyer"), "investor")
        for n in deal.get("investors") or []:
            add(n, "investor")
    elif t == "debt_financing":
        add(deal.get("buyer"), "lender")
        for n in deal.get("investors") or []:
            add(n, "lender")
    elif t in ("acquisition", "merger"):
        add(deal.get("buyer"), "acquirer")
        add(deal.get("seller"), "seller")
    elif t == "exit":
        add(deal.get("seller"), "seller")
        add(deal.get("buyer"), "acquirer")
    elif t == "fund_raise":
        add(deal.get("target"), "gp")
        for n in deal.get("investors") or []:
            add(n, "lp")
    return out


def profiles(deals: Iterable[dict]) -> dict[str, dict]:
    """Every party's profile, keyed by canonical name."""
    deals = list(deals)
    by_party: dict[str, list[tuple[dict, str]]] = defaultdict(list)
    for d in deals:
        for name, role in parties(d):
            by_party[name].append((d, role))
    out = {}
    for name, rows in by_party.items():
        out[name] = _profile(name, rows)
    return out


def _profile(name: str, rows: list[tuple[dict, str]]) -> dict:
    entry = registry_entry(name)
    roles = Counter(role for _, role in rows)
    disclosed = [d["amount_usd"] for d, _ in rows if d.get("amount_usd")]
    co = Counter()
    for d, _ in rows:
        for other, _role in parties(d):
            if other != name:
                co[other] += 1
    recent = sorted(rows, key=lambda r: r[0].get("announced") or "", reverse=True)
    return {
        "name": name,
        "type": entry.kind if entry else None,
        "hq": entry.hq if entry else None,
        "in_registry": entry is not None,
        "deal_count": len({d["id"] for d, _ in rows}),
        "roles": dict(roles),
        "disclosed_usd": round(sum(disclosed)),
        "disclosed_count": len(disclosed),
        "sectors": dict(Counter(d.get("sector") for d, _ in rows if d.get("sector")).most_common(8)),
        "countries": dict(Counter(c for d, _ in rows for c in (d.get("countries") or [])).most_common(10)),
        "deal_types": dict(Counter(d.get("deal_type") for d, _ in rows)),
        "co_investors": [{"name": n, "deals": k} for n, k in co.most_common(10)],
        "first_seen": min((d.get("announced") for d, _ in rows if d.get("announced")), default=None),
        "last_seen": max((d.get("announced") for d, _ in rows if d.get("announced")), default=None),
        "recent": [{"id": d["id"], "role": role, "deal_type": d.get("deal_type"), "target": d.get("target"),
                    "amount_usd": d.get("amount_usd"), "announced": d.get("announced"), "country": d.get("country"),
                    "headline": d.get("headline")} for d, role in recent[:15]],
    }


def profile(deals: Iterable[dict], name: str) -> Optional[dict]:
    """One party's profile (any alias works), or None if it appears in no deal."""
    target = canonical(name)
    rows = [(d, role) for d in deals for n, role in parties(d) if n == target]
    if not rows:
        key = normalise_name(name)
        rows = [(d, role) for d in deals for n, role in parties(d) if key and key in normalise_name(n)]
        if not rows:
            return None
        target = parties(rows[0][0])[0][0] if parties(rows[0][0]) else name
    return _profile(target, rows)


def leaderboard(deals: Iterable[dict], role: Optional[str] = None, kind: Optional[str] = None,
                limit: int = 50) -> list[dict]:
    """Most active parties, optionally by role (investor, lender, acquirer, seller, lp, gp) or registry type."""
    rows = []
    for p in profiles(deals).values():
        if role and not p["roles"].get(role):
            continue
        if kind and p["type"] != kind:
            continue
        rows.append(p)
    rows.sort(key=lambda p: (p["roles"].get(role, 0) if role else p["deal_count"], p["disclosed_usd"]), reverse=True)
    return [{k: p[k] for k in ("name", "type", "hq", "deal_count", "roles", "disclosed_usd", "countries", "last_seen")}
            for p in rows[:limit]]


def funds(deals: Iterable[dict]) -> list[dict]:
    """Fund raises and closes (GP activity) with their LPs, newest first."""
    out = []
    for d in deals:
        if d.get("deal_type") != "fund_raise":
            continue
        out.append({"id": d["id"], "fund_or_manager": d.get("target"), "stage": d.get("stage"),
                    "amount_usd": d.get("amount_usd"), "lps": [canonical(n) for n in d.get("investors") or []],
                    "announced": d.get("announced"), "country": d.get("country"), "headline": d.get("headline"),
                    "sources": d.get("sources")})
    return sorted(out, key=lambda f: f.get("announced") or "", reverse=True)
