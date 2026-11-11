"""
Daily social post drafts from the deal database, emailed to the owner for approval.

Every sentence is assembled from stored deal fields (parties, amount, round, country, sources); nothing is written
by a language model, so a draft can never state a figure the database does not hold. Nothing is posted anywhere:
the owner reads the drafts, edits them and publishes by hand.

Each morning's email carries:
  - Deal of the day: the largest disclosed deal announced in the window, as a LinkedIn post and an X post.
  - Roundup: up to five deals from the window in one post.
  - More deals for X: up to two further deals, one post each, with a fact from the database where one holds
    ("Proparco's first deal in Sudan that we track", "IFC's 6th disclosed deal in Africa this year").
  - Markets: the strongest sector this year in US dollars, the largest sector, and the day's biggest mover.
  - On Mondays, the week in African deals: count, disclosed total, top countries, top deals, most active investors.
  - On Fridays, a question for replies.
"""
from __future__ import annotations

import html
from collections import Counter
from datetime import date, timedelta
from typing import Optional

from src.data import africa_countries as ac
from src.engines import deal_sanity

APP = "https://deal-intelligence.app"
X_LIMIT = 280
X_LINK_LENGTH = 23            # X counts every link as 23 characters, whatever its length
HASHTAGS = "#AfricanTech #VentureCapital #PrivateEquity"


# ── Facts to words ───────────────────────────────────────────────────────────

def money(usd: Optional[float]) -> Optional[str]:
    if not usd or usd <= 0:
        return None
    if usd >= 1e9:
        return f"${usd / 1e9:.1f}B".replace(".0B", "B")
    if usd >= 1e6:
        return f"${usd / 1e6:.1f}M".replace(".0M", "M")
    return f"${usd / 1e3:.0f}K"


def country_name(code: Optional[str]) -> Optional[str]:
    c = ac.get(code) if code else None
    return c.name if c else None


def _distinct(names: list[str]) -> list[str]:
    """Drop a name that repeats another's start ("Victory Park Capital Advisors" after "Victory Park Capital")."""
    out: list[str] = []
    for n in names:
        if n and not any(n.lower().startswith(o.lower()) or o.lower().startswith(n.lower()) for o in out):
            out.append(n)
    return out


def _join(names: list[str]) -> str:
    names = _distinct(names)
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _investors(d: dict, limit: int = 3) -> tuple[str, list[str]]:
    """('led by', [names]) when leads are known, else ('from', [names])."""
    leads = [n for n in (d.get("lead_investors") or []) if n]
    if leads:
        return "led by", leads[:limit]
    return "from", [n for n in (d.get("investors") or []) if n][:limit]


def summary(d: dict) -> Optional[str]:
    """One plain sentence about the deal, or None when the record lacks the parties to say it."""
    kind, target, buyer, seller = d.get("deal_type"), d.get("target"), d.get("buyer"), d.get("seller")
    amount = money(d.get("amount_usd"))
    stake = d.get("stake_pct")
    if kind == "equity_funding" and target:
        rnd = d.get("round")
        what = " ".join(x for x in (amount, f"{rnd} round" if rnd and rnd != "undisclosed" else None) if x) or "new funding"
        verb, names = _investors(d)
        sep = ", " if verb == "led by" else " "
        return f"{target} raised {what}" + (f"{sep}{verb} {_join(names)}" if names else "")
    if kind == "debt_financing" and target:
        _, names = _investors(d)
        return f"{target} secured {amount + ' in ' if amount else ''}debt financing" + (f" from {_join(names)}" if names else "")
    if kind == "acquisition" and target and buyer:
        part = f"a {stake:g}% stake in {target}" if stake and stake < 100 else target
        return f"{buyer} acquired {part}" + (f" for {amount}" if amount else "")
    if kind == "exit" and target and seller:
        part = f"its {stake:g}% stake in {target}" if stake and stake < 100 else f"its stake in {target}"
        return f"{seller} sold {part}" + (f" to {buyer}" if buyer else "") + (f" for {amount}" if amount else "")
    if kind == "merger" and target and buyer:
        return f"{buyer} and {target} agreed to merge" + (f" in a {amount} deal" if amount else "")
    if kind == "ipo" and target:
        return f"{target} is going public" + (f", raising {amount}" if amount else "")
    if kind == "fund_raise" and target:
        return f"{target} closed {amount + ' ' if amount else ''}in commitments"
    if kind == "joint_venture" and target and buyer:
        return f"{buyer} formed a joint venture with {target}"
    return None


def source(d: dict) -> tuple[Optional[str], Optional[str]]:
    """(publisher, url) of the earliest dated source. A news-aggregator redirect is too long and opaque to post,
    so its link is left out and the publisher is named; the deal page lists every source."""
    srcs = sorted((s for s in d.get("sources") or [] if s.get("url")), key=lambda s: s.get("date") or "9999")
    direct = [s for s in srcs if "news.google.com" not in s["url"]]
    if direct:
        return direct[0].get("publisher"), direct[0]["url"]
    return (srcs[0].get("publisher"), None) if srcs else (None, None)


def deal_link(d: dict) -> str:
    """The deal's public page: readable without an account, so a shared link opens to the deal."""
    return f"{APP}/deals/{d['id']}"


def x_length(text: str) -> int:
    """Length as X counts it: each URL is 23 characters."""
    return sum(X_LINK_LENGTH if w.startswith(("http://", "https://")) else len(w) for w in text.split(" ")) \
        + text.count(" ")


# ── Choosing deals ───────────────────────────────────────────────────────────

def in_window(deals: list[dict], start: date, end: date) -> list[dict]:
    lo, hi = start.isoformat(), end.isoformat()
    return [d for d in deals if lo <= str(d.get("announced") or "")[:10] <= hi and summary(d)]


def ranked(deals: list[dict]) -> list[dict]:
    """Largest disclosed first; corroborated before single-source among equals."""
    return sorted(deals, key=lambda d: (d.get("amount_usd") or 0, len(d.get("sources") or [])), reverse=True)


# ── Drafts ───────────────────────────────────────────────────────────────────

def deal_of_the_day(d: dict) -> dict:
    line = summary(d)
    where = country_name(d.get("country"))
    sector = d.get("sector")
    publisher, url = source(d)
    context = " ".join(x for x in (f"Sector: {sector}." if sector else None, f"Market: {where}." if where else None) if x)
    linkedin = "\n\n".join(x for x in (
        f"Deal of the day: {line}.",
        context or None,
        (f"Source: {publisher or 'original report'}, {url}" if url else f"Source: {publisher}" if publisher else None),
        f"Every deal we track links to its sources. Explore the full record: {deal_link(d)}",
        HASHTAGS,
    ) if x)
    x = f"{line}. {deal_link(d)}"
    if where and x_length(f"{line} ({where}). {deal_link(d)}") <= X_LIMIT:
        x = f"{line} ({where}). {deal_link(d)}"
    return {"kind": "Deal of the day", "deal_ids": [d["id"]], "linkedin": linkedin,
            "x": x if x_length(x) <= X_LIMIT else None}


def _same_company(a: Optional[str], b: Optional[str]) -> bool:
    """'SA Fintech Yoco' and 'Yoco' are one company: every word of the shorter name is in the longer."""
    wa, wb = set((a or "").lower().split()), set((b or "").lower().split())
    return bool(wa and wb) and (wa <= wb or wb <= wa)


def roundup(deals: list[dict], label: str) -> Optional[dict]:
    top: list[dict] = []
    for d in ranked(deals):                  # one line per company: its largest deal in the window
        if not any(_same_company(d.get("target"), t.get("target")) for t in top):
            top.append(d)
        if len(top) == 5:
            break
    if len(top) < 2:
        return None
    lines = [f"{i}. {summary(d)}" + (f" ({country_name(d.get('country'))})" if country_name(d.get("country")) else "")
             for i, d in enumerate(top, 1)]
    linkedin = "\n\n".join([f"African deals, {label}:", "\n".join(lines),
                            f"Sources for every deal, plus investors and country data: {APP}/deals", HASHTAGS])
    x_lines, x = [], None
    for d in top:
        candidate = "\n".join([f"African deals, {label}:", *x_lines, f"- {summary(d)}", f"{APP}/deals"])
        if x_length(candidate) > X_LIMIT:
            break
        x_lines.append(f"- {summary(d)}")
        x = candidate
    return {"kind": "Roundup", "deal_ids": [d["id"] for d in top], "linkedin": linkedin, "x": x}


def week_in_review(deals: list[dict], start: date, end: date) -> Optional[dict]:
    if len(deals) < 3:
        return None
    total = sum(d.get("amount_usd") or 0 for d in deals)
    disclosed = sum(1 for d in deals if d.get("amount_usd"))
    countries = Counter(country_name(d.get("country")) for d in deals if country_name(d.get("country")))
    backers = Counter(n for d in deals for n in set((d.get("investors") or []) + (d.get("lead_investors") or [])) if n)
    top = ranked(deals)[:3]
    span = f"{start.strftime('%-d %b')} to {end.strftime('%-d %b %Y')}"
    parts = [f"The week in African deals ({span}):",
             f"{len(deals)} deals tracked" + (f", {money(total)} disclosed across {disclosed} of them" if total else "") + "."]
    if countries:
        parts.append("Most active markets: " + _join([f"{c} ({n})" for c, n in countries.most_common(3)]) + ".")
    parts.append("Largest deals:\n" + "\n".join(f"{i}. {summary(d)}" for i, d in enumerate(top, 1)))
    repeat = [(n, c) for n, c in backers.most_common(3) if c >= 2]
    if repeat:
        parts.append("Most active investors: " + _join([f"{n} ({c} deals)" for n, c in repeat]) + ".")
    parts += [f"Every figure links to its sources: {APP}/deals", HASHTAGS]
    x = f"The week in African deals: {len(deals)} tracked" + (f", {money(total)} disclosed" if total else "") \
        + (f". Busiest market: {countries.most_common(1)[0][0]}" if countries else "") + f". {APP}/deals"
    return {"kind": "Week in review", "deal_ids": [d["id"] for d in top], "linkedin": "\n\n".join(parts),
            "x": x if x_length(x) <= X_LIMIT else None}


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def deal_fact(d: dict, deals: list[dict], today: date) -> Optional[str]:
    """One sentence the database supports about a deal's lead backer: its first deal in this country among many
    we track, or its count of disclosed deals this year. None when nothing notable holds."""
    backers = [n for n in (d.get("lead_investors") or d.get("investors") or [d.get("buyer")]) if n][:1]
    if not backers or d.get("deal_type") not in ("equity_funding", "debt_financing"):
        return None
    who = backers[0]
    key = who.lower()
    theirs = [x for x in deals if any(isinstance(n, str) and n.lower() == key
                                      for n in (x.get("investors") or []) + [x.get("buyer")])]
    where = country_name(d.get("country"))
    if where and len(theirs) >= 8 and sum(1 for x in theirs if x.get("country") == d.get("country")) == 1:
        return f"It is {who}'s first deal in {where} that we track, out of {len(theirs)} across Africa."
    this_year = [x for x in theirs if str(x.get("announced") or "")[:4] == str(today.year)
                 and str(x.get("announced") or "")[:10] <= today.isoformat()]
    if len(this_year) >= 3:
        return f"It is {who}'s {_ordinal(len(this_year))} disclosed deal in Africa this year."
    return None


def deal_post(d: dict, deals: list[dict], today: date, kind: str) -> dict:
    """One deal as an X post: what happened, where, a fact where one holds, and the deal's page."""
    line, where, link = summary(d), country_name(d.get("country")), deal_link(d)
    fact = deal_fact(d, deals, today)
    for parts in ((f"{line}" + (f" ({where})" if where else "") + ".", fact, link),
                  (f"{line}" + (f" ({where})" if where else "") + ".", link), (f"{line}.", link)):
        x = "\n\n".join(p for p in parts if p)
        if x_length(x) <= X_LIMIT:
            return {"kind": kind, "deal_ids": [d["id"]], "x": x}
    return {"kind": kind, "deal_ids": [d["id"]], "x": None}


def _pct(v: float) -> str:
    return f"{abs(v) * 100:.0f}%"


def market_post(overview: Optional[dict]) -> Optional[dict]:
    """The strongest sector this year in US dollars, the largest sector, and the day's biggest mover, from the
    platform's market snapshot. A move above 50% in a day is left out as more likely a data error than news."""
    if not overview:
        return None
    sectors = [x for x in overview.get("sectors") or [] if x.get("shares", 0) >= 10 and x.get("ytd_usd") is not None]
    exchanges = (overview.get("coverage") or {}).get("exchanges")
    lines = []
    if sectors:
        best = max(sectors, key=lambda x: x["ytd_usd"])
        biggest = max(sectors, key=lambda x: x.get("mcap_usd") or 0)
        direction = "up" if best["ytd_usd"] >= 0 else "down"
        scope = f"the {exchanges} exchanges we track" if exchanges else "the exchanges we track"
        lines.append(f"African {best['sector'].lower()} stocks are {direction} {_pct(best['ytd_usd'])} this year in "
                     f"US dollar terms, the strongest sector across {scope}.")
        if biggest is not best and biggest.get("mcap_usd"):
            move = "up" if biggest["ytd_usd"] >= 0 else "down"
            lines.append(f"{biggest['sector']}, the largest at {money(biggest['mcap_usd'])} in market value, are "
                         f"{move} {_pct(biggest['ytd_usd'])}.")
    movers = [g for g in overview.get("gainers") or [] if g.get("chg_1d") and 0 < g["chg_1d"] <= 0.5]
    if movers:
        g = movers[0]
        where = country_name((overview.get("exchange_country") or {}).get(g.get("exchange"))) or None
        lines.append(f"Biggest gainer on the last trading day: {g['name']}" + (f" ({where})" if where else "")
                     + f", up {_pct(g['chg_1d'])}.")
    if not lines:
        return None
    x_lines = list(lines)                         # X drops lines to fit; LinkedIn keeps them all
    x = "\n\n".join(x_lines + [f"{APP}/markets"])
    while x_length(x) > X_LIMIT and len(x_lines) > 1:
        x_lines.pop()
        x = "\n\n".join(x_lines + [f"{APP}/markets"])
    linkedin = "\n\n".join(lines + [f"Prices, sectors and currencies across African exchanges: {APP}/markets",
                                     HASHTAGS])
    return {"kind": "Markets", "deal_ids": [], "linkedin": linkedin, "x": x if x_length(x) <= X_LIMIT else None}


QUESTIONS = [
    "Which African market will see the most venture deals next year?\n\nNigeria · Kenya · Egypt · South Africa",
    "What is the biggest obstacle to more African exits?\n\nFew buyers · Currency · Small IPO markets · Valuations",
    "Where will African fintech consolidation come from?\n\nBanks · Telcos · Other fintechs · Global players",
    "Which sector will attract the most private capital in Africa next year?\n\nFintech · Energy · Agriculture · Health",
    "Debt or equity: which will fund more African startups next year?",
    "Which African stock exchange deserves more global investor attention, and why?",
]


def question_post(today: date) -> dict:
    q = QUESTIONS[today.isocalendar()[1] % len(QUESTIONS)]
    return {"kind": "Question for replies", "deal_ids": [], "x": q, "linkedin": q}


def build(deals: list[dict], today: date, market: Optional[dict] = None, briefing: Optional[dict] = None) -> dict:
    """All of today's drafts. The daily window is yesterday and today (UTC), widened to three days when quiet.
    Deals the sanity checks flag are held out of every draft and listed for review instead."""
    window = in_window(deals, today - timedelta(days=1), today)
    label = "the last 24 hours"
    if len(window) < 2:
        window, label = in_window(deals, today - timedelta(days=3), today), "the last three days"
    flagged = deal_sanity.review(window)
    held_back = [{"id": d["id"], "summary": summary(d) or d.get("headline"), "reasons": flagged[d["id"]],
                  "link": deal_link(d)} for d in ranked(window) if d["id"] in flagged]
    window = [d for d in window if d["id"] not in flagged]
    drafts = []
    if window:
        top = ranked(window)
        drafts.append(deal_of_the_day(top[0]))
        chosen = [top[0]]
        for d in top[1:]:                         # two more companies, one post each
            if len(chosen) == 3:
                break
            if not any(_same_company(d.get("target"), c.get("target")) for c in chosen):
                chosen.append(d)
                drafts.append(deal_post(d, deals, today, f"More deals for X ({len(chosen) - 1} of 2)"))
        if (r := roundup(window, label)):
            drafts.append(r)
    if (m := market_post(market)):
        drafts.append(m)
    drafts += (briefing or {}).get("drafts") or []
    if today.weekday() == 4:
        drafts.append(question_post(today))
    if today.weekday() == 0:
        start, end = today - timedelta(days=7), today - timedelta(days=1)
        week = in_window(deals, start, end)
        week_flags = deal_sanity.review(week)
        if (w := week_in_review([d for d in week if d["id"] not in week_flags], start, end)):
            drafts.append(w)
    return {"date": today.isoformat(), "window": label, "deals_in_window": len(window), "drafts": drafts,
            "held_back": held_back, "briefing": (briefing or {}).get("sections") or []}


# ── Email ────────────────────────────────────────────────────────────────────

def render_email(result: dict) -> tuple[str, str, str]:
    """(subject, html, text)."""
    drafts = result["drafts"]
    day = date.fromisoformat(result["date"]).strftime("%-d %b %Y")
    subject = f"Post drafts and market briefing for {day}: {len(drafts)} posts ready" if drafts \
        else f"Post drafts and market briefing for {day}: no new deals"
    intro = ("Drafts from the deals tracked in " + result["window"] + ". Check each figure against its source, edit "
             "freely and post by hand. Nothing is published automatically.") if drafts else \
        "No deal in the last three days had enough detail for a post. Nothing to publish today."
    blocks, text = [], [subject, "", intro, ""]
    box = ("white-space:pre-wrap;font-family:ui-monospace,Menlo,monospace;font-size:13px;line-height:1.5;"
           "background:#f6f7f9;border:1px solid #e3e6ea;border-radius:8px;padding:14px;margin:6px 0 18px")
    for d in drafts:
        blocks.append(f'<h2 style="font-size:16px;margin:24px 0 4px">{html.escape(d["kind"])}</h2>')
        text += [f"== {d['kind']} ==", ""]
        for platform, key in (("LinkedIn", "linkedin"), ("X", "x")):
            if d.get(key):
                count = f" ({x_length(d[key])}/{X_LIMIT})" if key == "x" else ""
                blocks.append(f'<p style="margin:10px 0 0;color:#5b6470;font-size:12px">{platform}{count}</p>'
                              f'<div style="{box}">{html.escape(d[key])}</div>')
                text += [f"-- {platform}{count} --", d[key], ""]
    sections = result.get("briefing") or []
    if sections:
        blocks.append('<h2 style="font-size:18px;margin:32px 0 4px;border-top:1px solid #e3e6ea;padding-top:20px">'
                      'Market briefing</h2><p style="color:#5b6470;font-size:13px;margin:0 0 8px">From the platform\'s '
                      'latest market snapshot. For reading and for picking posts; check a figure before posting it.</p>')
        text += ["== Market briefing ==", ""]
        for sec in sections:
            blocks.append(f'<h3 style="font-size:14px;margin:18px 0 4px">{html.escape(sec["title"])}</h3>')
            if sec.get("note"):
                blocks.append(f'<p style="color:#5b6470;font-size:12px;margin:0 0 4px">{html.escape(sec["note"])}</p>')
            blocks.append('<ul style="font-size:13px;line-height:1.5;margin:0;padding-left:18px">'
                          + "".join(f"<li>{html.escape(line)}</li>" for line in sec["lines"]) + "</ul>")
            text += [f"-- {sec['title']} --", *[f"- {line}" for line in sec["lines"]], ""]
    held = result.get("held_back") or []
    if held:
        blocks.append(f'<h2 style="font-size:16px;margin:28px 0 4px">Held back for review ({len(held)})</h2>'
                      '<p style="color:#5b6470;font-size:13px;margin:0 0 8px">These looked wrong to the automatic '
                      'checks, so they are not in any draft. Open each to check it.</p>')
        text += [f"== Held back for review ({len(held)}) ==", ""]
        for h in held[:15]:
            reasons = "; ".join(h["reasons"])
            blocks.append(f'<p style="font-size:13px;margin:8px 0"><a href="{html.escape(h["link"])}">'
                          f'{html.escape(h["summary"] or h["id"])}</a><br><span style="color:#5b6470">'
                          f'{html.escape(reasons)}</span></p>')
            text += [f"- {h['summary']}", f"  {reasons}", f"  {h['link']}", ""]
    body = (f'<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#14171c;max-width:640px">'
            f'<h1 style="font-size:20px">{html.escape(subject)}</h1><p>{html.escape(intro)}</p>{"".join(blocks)}'
            f'<p style="color:#5b6470;font-size:12px;margin-top:28px">Sent by Deal Intelligence to its owner. '
            f'Turn this off by removing CONTENT_DRAFTS_TO from the API settings.</p></div>')
    return subject, body, "\n".join(text)
