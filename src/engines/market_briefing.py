"""
The markets half of the owner's morning email: every exchange, the day's movers, most traded shares, sectors,
currencies, Treasury bill auctions, policy rates, ETFs and company news, from the platform's own snapshots.

Like the deal drafts, every line is assembled from stored figures; nothing is written by a language model. A
one-day move above 50% is far more often a bad print than news, so such moves are listed for checking and kept out
of the movers and the post drafts.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from src.data import africa_countries as ac

APP = "https://deal-intelligence.app"
X_LIMIT = 280
IMPLAUSIBLE_DAY_MOVE = 0.5
POSTABLE_DAY_MOVE = 0.3        # thinly traded secondary listings swing hard; posts use only moves within 30%
TOP = 5

# Elections investors watch for a change in policy, the currency and deal timing: (country, name, kind, day, currency,
# exchange). INEC's revised timetable: presidential and National Assembly on 16 January 2027, governorship on 6 February.
ELECTIONS = (("NG", "Nigeria", "general election", date(2027, 1, 16), "NGN", "ngx"),)
ELECTION_LEAD_DAYS = 120       # the angle appears in the posts from four months before polling day
ELECTION_AFTER_DAYS = 30       # and stays for a month after, while markets price the result


def election(today: date) -> Optional[dict]:
    """The election in its window around `today`, with a hook for the posts, or None."""
    for code, name, kind, day, currency, exchange in ELECTIONS:
        days = (day - today).days
        if -ELECTION_AFTER_DAYS <= days <= ELECTION_LEAD_DAYS:
            when = f"{day.day} {day.strftime('%B %Y')}"
            hook = (f"{days} days to {name}'s {kind}" if days > 1 else
                    f"{name}'s {kind} is tomorrow" if days == 1 else
                    f"{name} votes today" if days == 0 else
                    f"{-days} day{'s' if days < -1 else ''} after {name}'s {kind}")
            countdown = (f"{days} days to go" if days > 1 else "polling day tomorrow" if days == 1 else
                         "polling day" if days == 0 else f"{-days} day{'s' if days < -1 else ''} after the vote")
            return {"country": code, "name": name, "kind": kind, "day": day, "days": days, "when": when,
                    "currency": currency, "exchange": exchange, "hook": hook, "countdown": countdown}
    return None


def _against_usd(v: float) -> str:
    """A currency's move against the dollar in words, so a rise is never read as the dollar rising."""
    return "flat against the dollar" if abs(v) < 0.0005 else \
        f"{'up' if v > 0 else 'down'} {pct(v, signed=False)} against the dollar"


def _tenor(r: dict) -> str:
    label = r.get("tenor_label") or f"{r.get('tenor_days')} days"
    return label[:-5] + "-day" if label.endswith(" days") else label


def _short_day(day: str) -> str:
    try:
        d = date.fromisoformat(str(day)[:10])
        return f"{d.day} {d.strftime('%b')}"
    except ValueError:
        return str(day)


def _election_figures(el: dict, overview: dict, instruments: dict, today: date) -> list[tuple[str, str]]:
    """(label, value) pairs for the election country: its currency, exchange, latest bill yield and policy rate."""
    out: list[tuple[str, str]] = []
    fx = next((c for c in overview.get("currencies") or [] if c.get("currency") == el["currency"]), None)
    if fx and fx.get("per_usd"):
        ytd = f" ({_against_usd(fx['ytd_vs_usd'])} this year)" if fx.get("ytd_vs_usd") is not None else ""
        out.append(("Naira" if el["currency"] == "NGN" else el["currency"], f"{fx['per_usd']:,.2f} per US${ytd}"))
    ex = next((e for e in overview.get("exchanges") or [] if e.get("exchange") == el["exchange"]), None)
    if ex and not ex.get("stale") and _fresh(ex.get("as_of"), today) and ex.get("ytd_local") is not None:
        usd_part = f", {pct(ex['ytd_usd'])} in US$" if ex.get("ytd_usd") is not None else ""
        out.append((el["exchange"].upper(), f"{pct(ex['ytd_local'])} this year{usd_part}"))
    for b in instruments.get("tbills") or []:
        if b.get("country") != el["country"] and b.get("country_name") != el["name"]:
            continue
        rows = [r for r in b.get("rows") or [] if _bill(r) is not None and r.get("auction_date")]
        if rows:
            latest = max(r["auction_date"] for r in rows)
            r = min((r for r in rows if r["auction_date"] == latest), key=lambda r: r.get("tenor_days") or 0)
            out.append((f"{_tenor(r)} T-bill", f"{_bill(r):.2f}% (auction {_short_day(latest)})"))
    rate = next((r for r in instruments.get("policy_rates") or []
                 if r.get("rate") is not None and (r.get("country") == el["country"] or r.get("country_name") == el["name"])), None)
    if rate:
        out.append(("Policy rate", f"{rate['rate']:g}%"))
    return out


def _country(code: Optional[str]) -> Optional[str]:
    c = ac.get(code) if code else None
    return c.name if c else None


def pct(v: Optional[float], signed: bool = True) -> str:
    if v is None:
        return "n/a"
    if abs(v) < 0.0005:
        return "0%"
    s = f"{v * 100:+.1f}%" if signed else f"{abs(v) * 100:.1f}%"
    return s.replace(".0%", "%")


def usd(v: Optional[float]) -> Optional[str]:
    if not v:
        return None
    if v >= 1e9:
        return f"${v / 1e9:.1f}B".replace(".0B", "B")
    if v >= 1e6:
        return f"${v / 1e6:.1f}M".replace(".0M", "M")
    return f"${v / 1e3:.0f}K"


def _x_len(text: str) -> int:
    return sum(23 if w.startswith(("http://", "https://")) else len(w) for w in text.split(" ")) + text.count(" ")


def _fresh(day: Optional[str], today: date, days: int = 5) -> bool:
    try:
        return date.fromisoformat(str(day)[:10]) >= today - timedelta(days=days)
    except ValueError:
        return False


def _exchange_names(overview: dict) -> dict[str, tuple[str, Optional[str]]]:
    return {e.get("exchange"): (e.get("name") or e.get("exchange", "").upper(), e.get("country"))
            for e in overview.get("exchanges") or []}


def _share(row: dict, names: dict) -> str:
    exch, country = names.get(row.get("exchange"), (str(row.get("exchange") or "").upper(), None))
    where = _country(country)
    return f"{row.get('name')} ({where or exch})"


# ── Sections ─────────────────────────────────────────────────────────────────

def exchanges_section(overview: dict, today: date) -> list[str]:
    lines = []
    tiles = sorted(overview.get("exchanges") or [], key=lambda e: -(e.get("mcap_usd") or 0))
    for e in tiles:
        if not _fresh(e.get("as_of"), today) or e.get("stale"):
            continue
        parts = []
        idx = e.get("index") or {}
        if idx.get("chg_1d") is not None and idx.get("date") == e.get("as_of"):
            parts.append(f"{idx.get('name') or 'index'} {pct(idx['chg_1d'])} on the day")
        if e.get("ytd_usd") is not None:
            parts.append(f"{pct(e['ytd_usd'])} this year in US$")
        if e.get("advancers") or e.get("decliners"):
            parts.append(f"{e['advancers']} up, {e['decliners']} down")
        if e.get("mcap_usd"):
            parts.append(f"{usd(e['mcap_usd'])} market value")
        if parts:
            name = e.get("name") or ""
            label = name if "(" in name else f"{name} ({_country(e.get('country')) or e.get('country')})"
            lines.append(f"{label}: " + "; ".join(parts))
    return lines


def movers(overview: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """(gainers, losers, implausible) with moves above 50% in a day set aside."""
    def ok(r):
        return r.get("chg_1d") is not None and abs(r["chg_1d"]) <= IMPLAUSIBLE_DAY_MOVE
    gainers = [r for r in overview.get("gainers") or [] if ok(r) and r["chg_1d"] > 0]
    losers = [r for r in overview.get("losers") or [] if ok(r) and r["chg_1d"] < 0]
    odd = [r for r in (overview.get("gainers") or []) + (overview.get("losers") or [])
           if r.get("chg_1d") is not None and abs(r["chg_1d"]) > IMPLAUSIBLE_DAY_MOVE]
    return gainers[:TOP], losers[:TOP], odd


def most_traded_section(overview: dict, names: dict) -> list[str]:
    rows = sorted((r for r in overview.get("most_traded") or [] if r.get("value_traded_usd")),
                  key=lambda r: -r["value_traded_usd"])[:TOP]
    return [f"{_share(r, names)}: {usd(r['value_traded_usd'])} traded, {pct(r.get('chg_1d'))}" for r in rows]


def sectors_section(overview: dict) -> list[str]:
    rows = sorted((s for s in overview.get("sectors") or [] if s.get("shares", 0) >= 10 and s.get("ytd_usd") is not None),
                  key=lambda s: -s["ytd_usd"])
    return [f"{s['sector']}: {pct(s['ytd_usd'])} this year in US$, {pct(s.get('chg_1d'))} on the day, "
            f"{s['shares']} shares, {usd(s.get('mcap_usd'))}" for s in rows]


_WATCHED_FX = ("NGN", "KES", "ZAR", "GHS", "EGP", "MAD", "XOF")


def currencies_section(overview: dict) -> list[str]:
    rows = [c for c in overview.get("currencies") or [] if c.get("ytd_vs_usd") is not None]
    if not rows:
        return []
    ranked = sorted(rows, key=lambda c: -c["ytd_vs_usd"])
    lines = ["Strongest against the dollar this year: " +
             ", ".join(f"{c['currency']} {pct(c['ytd_vs_usd'])}" for c in ranked[:3]),
             "Weakest: " + ", ".join(f"{c['currency']} {pct(c['ytd_vs_usd'])}" for c in ranked[::-1][:3])]
    watched = [c for c in rows if c["currency"] in _WATCHED_FX and c.get("per_usd")]
    if watched:
        lines.append("Rates per US$: " + ", ".join(
            f"{c['currency']} {c['per_usd']:,.2f}" for c in sorted(watched, key=lambda c: _WATCHED_FX.index(c["currency"]))))
    return lines


def _bill(row: dict) -> Optional[float]:
    v = row.get("true_yield") if row.get("true_yield") is not None else row.get("rate")
    return float(v) if v is not None else None


def tbills_section(instruments: dict, today: date) -> tuple[list[str], list[tuple[str, str, float, str]]]:
    """One line per country, newest auction first, and the countries with an auction in the last week."""
    out, recent = [], []
    blocks = []
    for b in instruments.get("tbills") or []:
        rows = [r for r in b.get("rows") or [] if _bill(r) is not None and r.get("auction_date")]
        if not rows:
            continue
        latest = max(r["auction_date"] for r in rows)
        rows = sorted((r for r in rows if r["auction_date"] == latest), key=lambda r: r.get("tenor_days") or 0)
        blocks.append((latest, b, rows))
    for latest, b, rows in sorted(blocks, key=lambda x: x[0], reverse=True):
        name = b.get("country_name") or b.get("country")
        tenors = ", ".join(f"{r.get('tenor_label') or str(r.get('tenor_days')) + ' days'} {_bill(r):.2f}%" for r in rows)
        new = _fresh(latest, today, 7)
        out.append(f"{name}{' (new this week)' if new else ''}: {tenors} (auction {latest})")
        if new:
            r = rows[0]
            recent.append((name, r.get("tenor_label") or f"{r.get('tenor_days')} days", _bill(r), latest))
    return out, recent


def policy_section(instruments: dict, today: date) -> list[str]:
    rows = [r for r in instruments.get("policy_rates") or [] if r.get("rate") is not None]
    rows.sort(key=lambda r: str(r.get("date") or ""), reverse=True)
    out = []
    for r in rows:
        note = "" if r.get("confirmed_by") else ", unconfirmed"
        out.append(f"{r.get('country_name') or r.get('country')}: {r['rate']:g}% (as of {r.get('date')}{note})")
    return out


def etf_section(instruments: dict) -> list[str]:
    rows = [r for r in (instruments.get("etfs") or {}).get("rows") or []
            if r.get("chg_1d") is not None and abs(r["chg_1d"]) <= IMPLAUSIBLE_DAY_MOVE]
    if not rows:
        return []
    up = sorted(rows, key=lambda r: -r["chg_1d"])[:3]
    down = sorted(rows, key=lambda r: r["chg_1d"])[:3]
    return (["Up: " + ", ".join(f"{r['name']} {pct(r['chg_1d'])}" for r in up),
             "Down: " + ", ".join(f"{r['name']} {pct(r['chg_1d'])}" for r in down)])


def news_section(events: list[dict], today: date) -> list[str]:
    """Credible company news from the last day, highest credibility first."""
    from src.engines import headline_translate
    rows = [e for e in events if _fresh(e.get("day"), today, 1) and (e.get("credibility") or 0) >= 0.6
            and (e.get("headline_en") or not headline_translate.is_arabic(e.get("headline")))]
    rows.sort(key=lambda e: (-(e.get("credibility") or 0), -(e.get("rule_score") or 0)))
    return [f"{e.get('headline_en') or e.get('headline')} ({_country(e.get('country')) or 'Africa'}, "
            f"{e.get('publisher') or 'source'})"
            for e in rows[:8]]


# ── Post drafts from the markets ─────────────────────────────────────────────

def currency_post(overview: dict, day: Optional[date] = None) -> Optional[dict]:
    page = f"{APP}/markets/currencies/{day.isoformat()}" if day else f"{APP}/markets"
    rows = [c for c in overview.get("currencies") or [] if c.get("ytd_vs_usd") is not None]
    if len(rows) < 4:
        return None
    ranked = sorted(rows, key=lambda c: -c["ytd_vs_usd"])
    best, worst = ranked[0], ranked[-1]
    el = election(day) if day else None
    fx = el and next((c for c in rows if c["currency"] == el["currency"] and c.get("per_usd")), None)
    if el and fx:
        lead = (f"{el['hook']}: the {'naira' if el['currency'] == 'NGN' else fx['currency']} is at "
                f"{fx['per_usd']:,.0f} per US$, {_against_usd(fx['ytd_vs_usd'])} this year.\n\n")
        text = (lead + f"Strongest in Africa: {', '.join(c['currency'] + ' ' + pct(c['ytd_vs_usd']) for c in ranked[:3])}\n"
                f"Weakest: {', '.join(c['currency'] + ' ' + pct(c['ytd_vs_usd']) for c in ranked[::-1][:3])}\n\n{page}")
        if _x_len(text) > X_LIMIT:
            text = lead + page
        return {"kind": "Currencies", "deal_ids": [], "x": text, "linkedin": text}
    text = (f"African currencies against the US dollar this year:\n\n"
            f"Strongest: {', '.join(c['currency'] + ' ' + pct(c['ytd_vs_usd']) for c in ranked[:3])}\n"
            f"Weakest: {', '.join(c['currency'] + ' ' + pct(c['ytd_vs_usd']) for c in ranked[::-1][:3])}\n\n"
            f"{page}")
    if _x_len(text) > X_LIMIT:
        text = f"Strongest African currency against the dollar this year: {best['currency']} {pct(best['ytd_vs_usd'])}. " \
               f"Weakest: {worst['currency']} {pct(worst['ytd_vs_usd'])}. {page}"
    return {"kind": "Currencies", "deal_ids": [], "x": text, "linkedin": text}


def tbill_post(recent: list[tuple[str, str, float, str]], day: Optional[date] = None) -> Optional[dict]:
    page = f"{APP}/markets/treasury-bills/{day.isoformat()}" if day else f"{APP}/markets"
    if len(recent) < 2:
        return None
    el = election(day) if day else None
    if el:                                       # the election country's auction leads
        recent = sorted(recent, key=lambda r: r[0] != el["name"])
    head = (f"{el['hook']}. This week's Treasury bill auctions in Africa:" if el
            else "This week's Treasury bill auctions in Africa:")
    lines = [f"{name}: {y:.2f}% ({tenor})" for name, tenor, y, _ in recent[:5]]
    text = head + "\n\n" + "\n".join(lines) + f"\n\n{page}"
    while _x_len(text) > X_LIMIT and len(lines) > 2:
        lines.pop()
        text = head + "\n\n" + "\n".join(lines) + f"\n\n{page}"
    return {"kind": "Treasury bills", "deal_ids": [], "x": text, "linkedin": text}


def movers_post(gainers: list[dict], losers: list[dict], names: dict, day: Optional[date] = None,
                overview: Optional[dict] = None) -> Optional[dict]:
    page = f"{APP}/markets/movers/{day.isoformat()}" if day else f"{APP}/markets"
    gainers = [r for r in gainers if abs(r["chg_1d"]) <= POSTABLE_DAY_MOVE]
    losers = [r for r in losers if abs(r["chg_1d"]) <= POSTABLE_DAY_MOVE]
    if not gainers or not losers:
        return None
    el = election(day) if day else None
    ex = el and next((e for e in (overview or {}).get("exchanges") or [] if e.get("exchange") == el["exchange"]
                      and not e.get("stale") and _fresh(e.get("as_of"), day) and e.get("ytd_local") is not None), None)
    lead = (f"{el['hook']}: the {el['exchange'].upper()} is {pct(ex['ytd_local'])} this year"
            + (f" ({pct(ex['ytd_usd'])} in US$)" if ex.get("ytd_usd") is not None else "") + ".\n\n") if ex else ""
    text = (lead + "Biggest movers on African exchanges on the last trading day:\n\n"
            + "\n".join(f"Up: {_share(r, names)} {pct(r['chg_1d'])}" for r in gainers[:2]) + "\n"
            + "\n".join(f"Down: {_share(r, names)} {pct(r['chg_1d'])}" for r in losers[:2])
            + f"\n\n{page}")
    if _x_len(text) > X_LIMIT and lead:
        text = (lead + f"Biggest movers in Africa: {_share(gainers[0], names)} {pct(gainers[0]['chg_1d'])}, "
                f"{_share(losers[0], names)} {pct(losers[0]['chg_1d'])}. {page}")
    if _x_len(text) > X_LIMIT:
        text = (f"Biggest movers on African exchanges: {_share(gainers[0], names)} {pct(gainers[0]['chg_1d'])}, "
                f"{_share(losers[0], names)} {pct(losers[0]['chg_1d'])}. {page}")
    return {"kind": "Stock movers", "deal_ids": [], "x": text if _x_len(text) <= X_LIMIT else None, "linkedin": text}


def election_post(overview: dict, instruments: dict, day: date) -> Optional[dict]:
    """The election country's money in one post: currency, exchange, bill yield and policy rate, counting down."""
    el = election(day)
    if not el:
        return None
    figures = _election_figures(el, overview, instruments, day)
    if len(figures) < 2:
        return None
    page = f"{APP}/markets/election/{day.isoformat()}"
    head = f"{el['name']} election watch, {el['countdown']} (polling day {el['when']}):"
    lines = [f"{k}: {v}" for k, v in figures]
    text = head + "\n\n" + "\n".join(lines) + f"\n\n{page}"
    while _x_len(text) > X_LIMIT and len(lines) > 2:
        lines.pop()
        text = head + "\n\n" + "\n".join(lines) + f"\n\n{page}"
    linkedin = (head + "\n\nWhat investors are watching:\n\n" + "\n".join(f"{k}: {v}" for k, v in figures)
                + f"\n\nTracked daily on Deal Intelligence: {page}")
    return {"kind": "Election watch", "deal_ids": [], "x": text if _x_len(text) <= X_LIMIT else None, "linkedin": linkedin}


# ── The whole briefing ───────────────────────────────────────────────────────

def build(overview: Optional[dict], instruments: Optional[dict], events: list[dict], today: date) -> dict:
    """{"sections": [{"title", "lines", "note"}], "drafts": [...]}; empty pieces are left out."""
    sections: list[dict] = []
    drafts: list[dict] = []
    overview, instruments = overview or {}, instruments or {}
    names = _exchange_names(overview)

    def add(title: str, lines: list[str], note: Optional[str] = None) -> None:
        if lines:
            sections.append({"title": title, "lines": lines, "note": note})

    if overview:
        add("Exchanges", exchanges_section(overview, today), "Largest first; exchanges without a recent price are left out.")
        gainers, losers, odd = movers(overview)
        add("Top gainers", [f"{_share(r, names)}: {pct(r['chg_1d'])}" for r in gainers])
        add("Top losers", [f"{_share(r, names)}: {pct(r['chg_1d'])}" for r in losers])
        add("Check before using", [f"{_share(r, names)}: {pct(r['chg_1d'])} in a day" for r in odd],
            "Moves above 50% in a day are usually a bad price, so they are kept out of the movers and the posts.")
        add("Most traded", most_traded_section(overview, names))
        add("Sectors", sectors_section(overview))
        add("Currencies", currencies_section(overview))
        if (p := movers_post(gainers, losers, names, today, overview)):
            drafts.append(p)
        if (p := currency_post(overview, today)):
            drafts.append(p)
    if instruments:
        bills, recent = tbills_section(instruments, today)
        add("Treasury bills", bills, "Latest auction in each country, newest first.")
        add("Policy rates", policy_section(instruments, today), "Most recent first.")
        add("ETFs", etf_section(instruments))
        if (p := tbill_post(recent, today)):
            drafts.append(p)
    if (el := election(today)) and (figures := _election_figures(el, overview, instruments, today)):
        sections.insert(0, {"title": f"Election watch: {el['hook']} ({el['when']})",
                            "lines": [f"{k}: {v}" for k, v in figures], "note": None})
        if (p := election_post(overview, instruments, today)):
            drafts.insert(0, p)
    add("Company news (last 24 hours)", news_section(events, today))
    return {"sections": sections, "drafts": drafts}
