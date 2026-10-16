"""
Source-grounded research: AI search and research reports.

Retrieval first, generation second:
  1. The question is parsed for countries, sectors, deal types, investors,
     companies and a time window.
  2. Evidence is retrieved from the deals database, the corporate-event feed,
     country and currency risk, investor profiles, and a live news search.
     Every item gets a number.
  3. The LLM (Claude or Groq) writes the answer using only those items and
     cites them as [n]. Citations are then checked: a number that does not
     match an item is removed, and every sentence without a valid citation is
     reported, so the reader sees exactly how much of the answer is grounded.
  4. With no LLM configured, the answer is a deterministic summary of the
     same evidence.

Country and sector research reports assemble the same evidence into
fixed sections; the LLM only writes the executive summary, under the same
citation rules.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
from collections import Counter
from datetime import date, timedelta
from typing import Callable, Iterable, Optional
from urllib.parse import quote

import httpx

from src.data.africa_countries import COUNTRIES, countries_in_text, get as get_country
from src.engines import country_risk as cr
from src.engines import deals as deals_mod
from src.engines import investors as inv
from src.engines import market_risk as mr

log = logging.getLogger(__name__)

_TYPE_WORDS = {
    "acquisition": r"acqui\w*|buyout|takeover|m&a|mergers?",
    "equity_funding": r"fund(ing|raise)|raised?|rounds?|venture|vc|series\s+[a-h]|seed|equity|startups?",
    "debt_financing": r"debt|loans?|credit|facilit\w+|bonds?|lend\w*|financing",
    "fund_raise": r"fund\s+close|first\s+close|final\s+close|fund\s+raising|lps?|limited\s+partners?|gps?|fund\s+managers?",
    "exit": r"exits?|divest\w*|sold",
    "ipo": r"ipos?|listings?|initial\s+public",
}
_SECTOR_WORDS = {name: rx for name, rx in deals_mod._SECTOR_RE}
_STOP = set("""a an and are as at be by for from has have how in is it its of on or that the this to was were what which
who will with about across between during over into than then there these those why when where most more many much
any all show list give tell me us our latest recent top biggest largest deals deal companies company africa african
dfi dfis series seed private markets market risk investment investments development finance""".split())
_REGION_ALIASES = {
    "Northern Africa": r"\b(?:north|northern)\s+africa\b",
    "Western Africa": r"\b(?:west|western)\s+africa\b",
    "Middle Africa": r"\b(?:middle|central)\s+africa\b",
    "Eastern Africa": r"\b(?:east|eastern)\s+africa\b",
    "Southern Africa": r"\bsouthern\s+africa\b",
}


def _terms(q: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9&'-]{3,}", q.lower()) if t not in _STOP]


def parse_question(q: str, today: Optional[date] = None) -> dict:
    today = today or date.today()
    regions = [region for region, pattern in _REGION_ALIASES.items() if re.search(pattern, q, re.IGNORECASE)]
    countries = [c.iso2 for c in countries_in_text(q)]
    countries.extend(c.iso2 for c in COUNTRIES if c.region in regions and c.iso2 not in countries)
    types = [t for t, rx in _TYPE_WORDS.items() if re.search(rf"\b(?:{rx})\b", q, re.IGNORECASE)]
    sectors = [s for s, rx in _SECTOR_WORDS.items() if rx.search(q)]
    investors = []
    for entry in inv.REGISTRY:
        for n in (entry.name, *entry.aliases):
            if re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", q, 0 if n.isupper() else re.IGNORECASE):
                investors.append(entry.name)
                break
    since = until = None
    m = re.search(r"\b(?:last|past)\s+(\d+)\s+(day|week|month|year)s?\b", q, re.IGNORECASE)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        since = today - timedelta(days=n * {"day": 1, "week": 7, "month": 30, "year": 365}[unit])
    elif re.search(r"\bthis\s+year\b", q, re.IGNORECASE):
        since, until = date(today.year, 1, 1), today
    elif re.search(r"\blast\s+year\b", q, re.IGNORECASE):
        since, until = date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    elif re.search(r"\bpast\s+year\b", q, re.IGNORECASE):
        since = today - timedelta(days=365)
    years = re.findall(r"\b(20\d{2})\b", q)
    if years and not since:
        since, until = date(int(min(years)), 1, 1), date(int(max(years)), 12, 31)
    # Keep explicit company names even at the start of a question, while ignoring
    # interrogatives and generic market vocabulary that is capitalised by title case.
    companies = []
    for phrase in re.findall(r"(?<![.?!]\s)\b([A-Z][\w&'-]+(?:\s+[A-Z][\w&'-]+){0,3})", q):
        words = re.findall(r"[a-z0-9]+", phrase.lower())
        if (countries_in_text(phrase) or inv.canonical(phrase) in investors or not words
                or all(word in _STOP for word in words)
                or any(pattern.search(phrase) for pattern in _SECTOR_WORDS.values())
                or any(re.fullmatch(pattern, phrase, re.IGNORECASE) for pattern in _REGION_ALIASES.values())):
            continue
        companies.append(phrase)
    kinds = [k for k, rx in (("dfi", r"\b(dfis?|development\s+finance)\b"), ("multilateral", r"\bmultilateral"),
                             ("private_equity", r"\bprivate\s+equity\b|\bpe\s+firms?\b"),
                             ("venture_capital", r"\bventure\s+capital|\bvcs?\b"), ("sovereign", r"\bsovereign\s+wealth"))
             if re.search(rx, q, re.IGNORECASE)]
    return {"countries": countries, "regions": regions, "deal_types": types, "sectors": sectors,
            "investors": investors, "investor_kinds": kinds,
            "companies": companies[:4], "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None, "terms": _terms(q)}


def _score(text: str, terms: list[str]) -> int:
    t = text.lower()
    return sum(1 for w in terms if w in t)


def _date_in_scope(value: Optional[str], parsed: dict) -> bool:
    if not parsed["since"] and not parsed["until"]:
        return True
    try:
        day = date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return False
    return (not parsed["since"] or day.isoformat() >= parsed["since"]) and (
        not parsed["until"] or day.isoformat() <= parsed["until"]
    )


def _matches_company(name: str, deal: dict) -> bool:
    tokens = deals_mod.normalise_name(name).split()
    if not tokens:
        return False
    fields = [deal.get("target"), deal.get("buyer"), deal.get("seller"), deal.get("headline"),
              *(deal.get("investors") or [])]
    return any(all(token in deals_mod.normalise_name(str(field)).split() for token in tokens)
               for field in fields if field)


def _fmt_usd(v: Optional[float]) -> str:
    if not v:
        return "undisclosed"
    for unit, div in (("bn", 1e9), ("m", 1e6), ("k", 1e3)):
        if abs(v) >= div:
            return f"${v / div:.1f}{unit}".replace(".0" + unit, unit)
    return f"${v:,.0f}"


_KIND_LABEL = {"dfi": "development finance institution", "multilateral": "multilateral development bank",
               "private_equity": "private equity firm", "venture_capital": "venture capital firm", "growth": "growth investor",
               "sovereign": "sovereign wealth fund", "pension": "pension fund", "accelerator": "accelerator"}


def _who(name: str) -> str:
    """Name with its registry type, so the model need not know who a DFI is."""
    entry = inv.registry_entry(name)
    return f"{name} ({_KIND_LABEL.get(entry.kind, entry.kind)})" if entry else name


def _deal_text(d: dict) -> str:
    parts = [f"{d['deal_type'].replace('_', ' ')} ({d.get('stage')})", f"target: {d.get('target') or 'n/a'}"]
    if d.get("buyer"):
        parts.append(f"buyer/lead/lender: {_who(d['buyer'])}")
    if d.get("investors"):
        parts.append(f"investors: {', '.join(_who(n) for n in d['investors'][:6])}")
    parts.append(f"amount: {_fmt_usd(d.get('amount_usd'))}")
    if d.get("round"):
        parts.append(f"round: {d['round']}")
    if d.get("stake_pct"):
        parts.append(f"stake: {d['stake_pct']}%")
    val = d.get("reported_valuation_usd") or d.get("implied_valuation_usd")
    if val:
        parts.append(f"valuation: {_fmt_usd(val)}")
    parts.append(f"country: {d.get('country') or 'Africa'}; sector: {d.get('sector') or 'n/a'}")
    return "; ".join(parts) + f". Headline: {d.get('headline')}"


def _news_items(query: str, country: Optional[str], limit: int = 8, client: Optional[httpx.Client] = None,
                since: Optional[str] = None, until: Optional[str] = None) -> list[dict]:
    c = get_country(country) if country else None
    date_scope = " ".join(filter(None, [
        f"after:{since}" if since else None,
        f"before:{until}" if until else None,
    ])) or "when:90d"
    search_query = f"{query} {date_scope}"
    url = (c.news_url(search_query) if c else
           f"https://news.google.com/rss/search?q={quote(search_query + ' Africa')}&hl=en-GB&gl=GB&ceid=GB:en")
    from src.engines.market_feed import parse_feed
    try:
        r = (client or httpx.Client(timeout=15, follow_redirects=True)).get(url)
        return parse_feed(r.text)[:limit]
    except Exception as e:
        log.warning("research news search failed: %s", e)
        return []


def retrieve(question: str, deals: Iterable[dict] = (), events: Iterable[dict] = (), briefs: Iterable[dict] = (),
             live_news: bool = True, news: Optional[Callable[[str, Optional[str]], list[dict]]] = None,
             today: Optional[date] = None, max_items: int = 30) -> tuple[dict, list[dict]]:
    """(parsed question, numbered evidence items)."""
    p = parse_question(question, today)
    deals, events = list(deals), list(events)
    items: list[dict] = []

    def add(kind: str, title: str, text: str, url: Optional[str] = None, day: Optional[str] = None,
            source: Optional[str] = None) -> None:
        items.append({"n": len(items) + 1, "kind": kind, "title": title, "text": text, "url": url, "date": day,
                      "source": source})

    # Deals: filtered by the parsed scope, ranked by term overlap then recency.
    scope = []
    for d in deals:
        if p["countries"] and not set(p["countries"]) & set(d.get("countries") or [d.get("country")]):
            continue
        if p["deal_types"] and d.get("deal_type") not in p["deal_types"]:
            continue
        if p["sectors"] and d.get("sector") not in p["sectors"]:
            continue
        if not _date_in_scope(d.get("announced"), p):
            continue
        if p["investors"] and not set(p["investors"]) & {n for n, _ in inv.parties(d)}:
            continue
        if p["investor_kinds"]:
            kinds = set(p["investor_kinds"]) | ({"multilateral"} if "dfi" in p["investor_kinds"] else set())
            if not any((inv.registry_entry(n) or inv.Investor("", "", "")).kind in kinds for n, _ in inv.parties(d)):
                continue
        if p["companies"] and not any(_matches_company(c, d) for c in p["companies"]):
            continue
        scope.append(d)
    scope.sort(key=lambda d: (_score(_deal_text(d), p["terms"]), d.get("announced") or ""), reverse=True)
    if scope:
        total = sum(d.get("amount_usd") or 0 for d in scope)
        by_type = Counter(d["deal_type"] for d in scope)
        by_country = Counter(d.get("country") or "pan-African" for d in scope)
        add("statistics", "Deals in scope (computed from the deals database)",
            f"{len(scope)} deals; disclosed value {_fmt_usd(total)} across {sum(1 for d in scope if d.get('amount_usd'))} "
            f"with amounts; by type: {dict(by_type)}; by country: {dict(by_country.most_common(8))}; "
            f"period: {min(d.get('announced') or '' for d in scope)} to {max(d.get('announced') or '' for d in scope)}.",
            source="Deals database")
    for d in scope[:12]:
        src = (d.get("sources") or [{}])[0]
        add("deal", d.get("headline") or d.get("target") or "deal", _deal_text(d), src.get("url"), d.get("announced"),
            src.get("publisher") or "news")

    # Corporate events.
    ev = [e for e in events
          if (not p["countries"] or set(p["countries"]) & set(e.get("countries") or [e.get("country")]))
          and (not p["sectors"] or e.get("sector") in p["sectors"])
          and _date_in_scope(e.get("day"), p)]
    ev.sort(key=lambda e: (_score(e["headline"], p["terms"]), e.get("day") or ""), reverse=True)
    for e in ev[:8]:
        add("event", e["headline"], f"{e['signal_type'].replace('_', ' ')} event"
            + (f", direction {e['direction']}" if e.get("direction") else "") + f"; country {e.get('country') or 'n/a'}",
            e.get("url"), e.get("day"), e.get("publisher"))

    # Country and currency risk.
    for code in ([] if p["regions"] else p["countries"][:3]):
        c = get_country(code)
        risk = cr.assess(c, fx=lambda _: None)
        comps = ", ".join(f"{x['name'].replace('_', ' ')} risk {x['risk']}" for x in risk["components"] if x["risk"] is not None)
        add("country_risk", f"{c.name} country risk", f"score {risk['score']}/100 ({risk['tier']}), coverage "
            f"{risk['coverage']:.0%}; component risk scores (0 = lowest risk, 100 = highest): {comps}. "
            f"World Bank data retrieved {risk['data_as_of']}.",
            "https://data.worldbank.org/country/" + c.iso2, risk["data_as_of"], "World Bank WGI/WDI")
        cur = mr.currency_risk(c.currency, fx=lambda _: None)
        add("currency_risk", f"{c.currency} currency risk", f"regime: {cur['regime']}; depreciation against the US "
            f"dollar last year {cur['last_year_depreciation_pct']}% (negative means the currency strengthened); five-year "
            f"annualised depreciation {cur['five_year_annualised_depreciation_pct']}%; currency risk score {cur['score']}/100 "
            f"({cur['tier']}).", None, None, "World Bank official exchange rates")

    # Investor profiles.
    investor_profiles = [inv.profile(scope, name) for name in p["investors"][:3]]
    kinds = set(p["investor_kinds"])
    if "dfi" in kinds:
        kinds.add("multilateral")
    for kind in sorted(kinds):
        investor_profiles.extend(inv.leaderboard(scope, kind=kind, limit=6))
    unique_profiles = {profile["name"]: profile for profile in investor_profiles if profile}
    ranked_profiles = sorted(unique_profiles.values(), key=lambda profile: profile["deal_count"], reverse=True)
    for prof in ranked_profiles[:6]:
        add("investor", f"{prof['name']} activity", f"{prof['deal_count']} deals; roles {prof['roles']}; disclosed "
            f"{_fmt_usd(prof['disclosed_usd'])}; countries {prof['countries']}; last seen {prof['last_seen']}.",
            source="Deals database")

    # Company briefs (signal analysis) that match the question.
    for b in briefs:
        if p["companies"] and any(deals_mod.normalise_name(c) in deals_mod.normalise_name(b.get("company", ""))
                                  for c in p["companies"]):
            sigs = (b.get("brief") or {}).get("detected_signals", [])
            add("brief", f"Signal brief: {b.get('company')}", f"severity {b.get('severity')}; signals: "
                + "; ".join(f"{s.get('signal_type')} ({s.get('severity')})" for s in sigs[:6]),
                None, (b.get("created_at") or "")[:10], "Deal Intelligence brief")

    # Live news.
    if live_news and len(items) < max_items:
        query_terms = p["companies"][:2] or p["terms"][:5]
        query = " ".join([*p["regions"][:1], *query_terms]) or question[:80]
        news_country = p["countries"][0] if len(p["countries"]) == 1 and not p["regions"] else None
        news_search = news or (lambda q, c: _news_items(q, c, since=p["since"], until=p["until"]))
        for it in news_search(query, news_country):
            if len(items) >= max_items:
                break
            if not _date_in_scope(it.get("date"), p):
                continue
            add("news", it["title"], it.get("snippet") or it["title"], it.get("url"), it.get("date"), it.get("publisher"))
    return p, items[:max_items]


SYSTEM = """You are a research analyst covering African companies, private markets and country risk.
Answer the question using ONLY the numbered evidence items provided. Rules:
- Every factual sentence must end with one or more citations like [3] or [2][5] pointing at the items it relies on.
- Do not use outside knowledge, do not estimate figures that are not in the items, and do not invent names.
- If the items do not answer the question, say so plainly and state what evidence is missing.
- Cite with square brackets only, e.g. [4], never other bracket styles.
- Be concise: a short direct answer, then the key supporting points. Use US dollars as given in the items."""


def _evidence_block(items: list[dict]) -> str:
    return "\n".join(f"[{i['n']}] ({i['kind']}; {i.get('source') or ''}; {i.get('date') or 'undated'}) "
                     f"{i['title']} | {i['text']}" for i in items)


_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\-*•])")
_CITE = re.compile(r"\[(\d{1,3})\]")


def normalise_citations(text: str) -> str:
    """【3】, [2, 5], [2-4] and (3) styles -> [3], [2][5], [2][3][4]."""
    text = re.sub(r"【\s*(\d{1,3})\s*】", r"[\1]", text)

    def expand(m: re.Match) -> str:
        nums: list[int] = []
        for part in re.split(r"\s*,\s*", m.group(1)):
            if "-" in part or "–" in part:
                a, b = re.split(r"[-–]", part)
                nums += list(range(int(a), int(b) + 1)) if int(b) - int(a) < 10 else [int(a), int(b)]
            else:
                nums.append(int(part))
        return "".join(f"[{n}]" for n in nums)
    return re.sub(r"\[(\d{1,3}(?:\s*[,\-–]\s*\d{1,3})+)\]", expand, text)


_NO_CLAIM = re.compile(r"(?i)\b(no|not)\b.{0,80}\b(evidence|items?|provided|available|listed|recorded)\b"
                       r"|\b(evidence|items?)\b.{0,40}\b(do|does)\s+not\b")


def _segments(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = re.sub(r"^[-*•\s]+", "", line.strip())
        if not line or line.startswith("#") or re.fullmatch(r"[*_]{1,3}[^*_]+[*_]{1,3}:?", line) or line.endswith(":"):
            continue
        out += [s.strip() for s in _SENTENCE.split(line) if len(s.strip()) > 25]
    return out


def validate_citations(text: str, n_items: int) -> dict:
    """Remove citations to items that do not exist; report factual sentences without a valid citation."""
    text = normalise_citations(text)
    invalid = sorted({int(n) for n in _CITE.findall(text) if not 1 <= int(n) <= n_items})
    clean = _CITE.sub(lambda m: m.group(0) if 1 <= int(m.group(1)) <= n_items else "", text)
    factual = [s for s in _segments(clean) if not _NO_CLAIM.search(s)]
    uncited = [s for s in factual if not _CITE.search(s)]
    cited = sorted({int(n) for n in _CITE.findall(clean)})
    return {"text": clean, "invalid_citations_removed": invalid, "cited_items": cited,
            "sentences": len(factual), "uncited_sentences": uncited,
            "grounded_share": round(1 - len(uncited) / len(factual), 2) if factual else 1.0}


def deterministic_answer(question: str, parsed: dict, items: list[dict]) -> str:
    if not items:
        return "No evidence in the deals database, event feed or news matched this question."
    lines = []
    stats = next((i for i in items if i["kind"] == "statistics"), None)
    if stats:
        lines.append(f"{stats['text']} [{stats['n']}]")
    for kind, label in (("deal", "Relevant deals"), ("investor", "Investors"), ("country_risk", "Country risk"),
                        ("currency_risk", "Currency risk"), ("event", "Corporate events"), ("news", "Recent news")):
        rows = [i for i in items if i["kind"] == kind]
        if rows:
            lines.append(f"\n{label}:")
            lines += [f"- {i['title']}" + (f" ({i['date']})" if i.get("date") else "") + f" [{i['n']}]" for i in rows[:8]]
    return "\n".join(lines)


def evidence_coverage(items: list[dict]) -> list[dict]:
    """Summarise retrieved evidence and its newest source date without implying completeness."""
    kinds = sorted({item["kind"] for item in items})
    return [
        {
            "kind": kind,
            "items": sum(1 for item in items if item["kind"] == kind),
            "latest_source_date": max(
                (str(item["date"])[:10] for item in items if item["kind"] == kind and item.get("date")),
                default=None,
            ),
        }
        for kind in kinds
    ]


def answer(question: str, items: list[dict], parsed: Optional[dict] = None, llm: Optional[Callable] = None) -> dict:
    """Grounded answer. llm(system, user, max_tokens) -> text; None uses the configured router or falls back."""
    parsed = parsed or parse_question(question)
    model = None
    if llm is None:
        try:
            from src.agents.signal_agent import _call_llm, _get_llm_client, _model_label
            client, provider = _get_llm_client()

            def llm(system: str, user: str, max_tokens: int) -> str:     # noqa: E306
                return _call_llm(client, provider, system, user, max_tokens)
            model_of = lambda: _model_label(client, provider)            # noqa: E731
        except Exception as e:
            log.info("research without LLM: %s", e)
            llm, model_of = None, None
    else:
        model_of = lambda: "custom"                                       # noqa: E731
    if llm is None or not items:
        text = deterministic_answer(question, parsed, items)
        return {"answer": text, "mode": "deterministic", "model": None, **_validation_summary(text, items)}
    user = f"Question: {question}\n\nEvidence items:\n{_evidence_block(items)}\n\nAnswer with citations."
    try:
        text = llm(SYSTEM, user, 1200)
        model = model_of() if model_of else None
    except Exception as e:
        log.warning("research LLM call failed: %s", e)
        text = deterministic_answer(question, parsed, items)
        return {"answer": text, "mode": "deterministic", "model": None, **_validation_summary(text, items)}
    v = validate_citations(text, len(items))
    return {"answer": v["text"], "mode": "llm", "model": model, "validation": v}


def _validation_summary(text: str, items: list[dict]) -> dict:
    return {"validation": validate_citations(text, len(items))}


def research(question: str, deals: Iterable[dict] = (), events: Iterable[dict] = (), briefs: Iterable[dict] = (),
             live_news: bool = True, llm: Optional[Callable] = None, news=None, today: Optional[date] = None) -> dict:
    parsed, items = retrieve(question, deals, events, briefs, live_news=live_news, news=news, today=today)
    result = answer(question, items, parsed, llm)
    return {"question": question, "parsed": parsed, "evidence": items,
            "evidence_coverage": evidence_coverage(items), **result}


# ── Research reports ──────────────────────────────────────────────────────────

def _section(title: str, rows: list[str]) -> str:
    return f"## {title}\n\n" + ("\n".join(rows) if rows else "_No evidence in the sources for this section._") + "\n"


def country_report(code: str, deals: Iterable[dict] = (), events: Iterable[dict] = (),
                   llm: Optional[Callable] = None, live_news: bool = True, news=None) -> dict:
    c = get_country(code)
    if c is None:
        raise ValueError(f"unknown country {code}")
    deals, events = list(deals), list(events)
    q = f"Private markets, deals and risk in {c.name}"
    parsed, items = retrieve(q, deals, events, live_news=live_news, news=news)
    risk = cr.assess(c, fx=lambda _: None)
    cur = mr.currency_risk(c.currency, fx=lambda _: None)
    cdeals = deals_mod.search(deals, country=c.iso2, limit=500)
    top_inv = inv.leaderboard(cdeals, limit=8)
    md = [f"# {c.name}: private markets and risk\n",
          f"Region: {c.region}. Currency: {c.currency} ({cur['regime']}). Exchange: {c.exchange or 'none'}. "
          f"Central bank: {c.central_bank}. Securities regulator: {c.securities_regulator or 'n/a'}.\n"]
    summary = answer(f"Summarise the investment environment in {c.name}: deal activity, investors, and risks.",
                     items, parsed, llm)
    md.append(_section("Executive summary", [summary["answer"]]))
    md.append(_section("Country risk", [f"Score **{risk['score']}** ({risk['tier']}), data coverage {risk['coverage']:.0%}."]
                       + [f"- {x['name'].replace('_', ' ')}: {x['risk']} (weight {x['weight']}; {x['formula']})"
                          for x in risk["components"]]))
    md.append(_section("Currency", [f"Regime: {cur['regime']} ({cur['regime_note']}). Last-year depreciation vs USD: "
                                    f"{cur['last_year_depreciation_pct']}%; five-year annualised: "
                                    f"{cur['five_year_annualised_depreciation_pct']}%. Score {cur['score']} ({cur['tier']})."]))
    by_type = Counter(d["deal_type"] for d in cdeals)
    md.append(_section("Deal activity", [f"{len(cdeals)} deals recorded; disclosed value "
                                         f"{_fmt_usd(sum(d.get('amount_usd') or 0 for d in cdeals))}; by type {dict(by_type)}."]
                       + [f"- {d.get('announced')}: {d.get('headline')}" for d in cdeals[:15]]))
    md.append(_section("Most active investors", [f"- {r['name']}: {r['deal_count']} deals, roles {r['roles']}" for r in top_inv]))
    md.append(_section("Sources", [f"[{i['n']}] {i['title']} {i.get('url') or ''}" for i in items]))
    return {"title": f"{c.name}: private markets and risk", "markdown": "\n".join(md), "evidence": items,
            "summary": summary, "country_risk": risk, "currency_risk": cur}


def sector_report(sector: str, deals: Iterable[dict] = (), events: Iterable[dict] = (), country: Optional[str] = None,
                  llm: Optional[Callable] = None, live_news: bool = True, news=None) -> dict:
    deals, events = list(deals), list(events)
    where = get_country(country).name if country and get_country(country) else "Africa"
    q = f"{sector.replace('_', ' ')} deals and risk in {where}"
    parsed, items = retrieve(q, deals, events, live_news=live_news, news=news)
    srisk = mr.sector_risk(sector, events, deals, country=country)
    sdeals = deals_mod.search(deals, sector=sector, country=country, limit=500)
    comps = deals_mod.comparables(sdeals, sector=sector, country=country, deal_type="equity_funding")
    summary = answer(f"Summarise {sector.replace('_', ' ')} activity in {where}: deals, investors, valuations and risks.",
                     items, parsed, llm)
    md = [f"# {sector.replace('_', ' ').title()} in {where}\n",
          _section("Executive summary", [summary["answer"]]),
          _section("Sector risk", [f"Score **{srisk['score']}** ({srisk['tier']}) from {srisk['adverse_events']} adverse "
                                   f"events, {srisk['other_events']} other events and {srisk['deals']} deals in "
                                   f"{srisk['window_days']} days" + (" (low sample)" if srisk["low_sample"] else "") + "."]),
          _section("Deals", [f"- {d.get('announced')}: {d.get('headline')}" for d in sdeals[:20]]),
          _section("Funding round sizes", [f"{comps['size_usd']}" if comps["size_usd"] else ""]),
          _section("Most active investors", [f"- {r['name']}: {r['deal_count']} deals" for r in inv.leaderboard(sdeals, limit=8)]),
          _section("Sources", [f"[{i['n']}] {i['title']} {i.get('url') or ''}" for i in items])]
    return {"title": f"{sector} in {where}", "markdown": "\n".join(md), "evidence": items, "summary": summary,
            "sector_risk": srisk}
