"""
Evidence for a valuation's inputs.

A source URL only says where a figure is claimed to come from. This module checks each input against something
it can verify:

  * price, currency and shares outstanding against the exchange's own daily close and published shares (the market
    snapshot);
  * statement figures against the figures parsed from the company's filing, when the profile has one;
  * otherwise against the cited document itself: it is fetched (public hosts only, size and time bounded), and
    each figure is looked for in the units filings use (units, thousands, millions, billions), together with the
    company's name and the period;
  * the source's standing: an exchange or regulator filing, the company's own website, or another site;
  * freshness: a statement period over 18 months old or a price over 7 days old.

Each field gets a status: "verified" (matches exchange data, or the current-period line of the filing parsed as a
statement, whether from the profile or the cited document itself), "found" (appears on the line labelled as that
item in an official document), "found_unlabelled" (the number appears, but not under its label: not counted),
"not_found", "mismatch", or "unchecked". A cheap or expensive verdict is allowed only when the
price is verified and every statement figure is verified or found, with nothing mismatched or stale.
"""
from __future__ import annotations

import html as html_mod
import ipaddress
import re
from datetime import date
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

import httpx

MAX_BYTES = 12_000_000
PRICE_TOLERANCE = 0.02
SHARES_TOLERANCE = 0.05
FILING_TOLERANCE = 0.01
STATEMENT_MAX_AGE_DAYS = 548
PRICE_MAX_AGE_DAYS = 7

# Exchanges, their filing services and securities regulators.
OFFICIAL_DOMAINS = (
    "ngxgroup.com", "nse.co.ke", "jse.co.za", "egx.com.eg", "casablanca-bourse.com", "brvm.org", "gse.com.gh",
    "stockexchangeofmauritius.com", "bvmt.com.tn", "bse.co.bw", "dse.co.tz", "luse.co.zm", "mse.co.mw", "nsx.com.na",
    "rse.rw", "zse.co.zw", "use.or.ug", "esx.et", "vfex.exchange", "sec.gov", "sec.gov.ng", "cma.or.ke",
    "fsca.co.za", "fra.gov.eg", "ammc.ma", "crepmf.org", "sec.gov.gh", "fscmauritius.org", "cmsa.go.tz",
    "seczambia.org.zm", "rbm.mw", "namfisa.com.na", "cma.rw", "seczim.co.zw", "cmauganda.co.ug",
)
_FIELDS = {"fcf": ("fcff", "unlevered_free_cash_flow", "free_cash_flow"), "cash": ("cash",), "debt": ("total_debt",),
           "dividend_per_share": ("annual_dividend_per_share", "dividend_per_share")}
# The line labels each figure is reported under, in English and French filings.
_LABELS = {
    "cash": r"cash and (?:cash )?equivalents|cash and bank|cash at bank|bank balances and cash|tr[ée]sorerie",
    "debt": r"borrowings|loans? (?:and|&) (?:borrowings|advances payable)|bank loans|interest[- ]bearing|debt|"
            r"bonds? (?:in )?issue|notes? payable|lease liabilities|emprunts|dettes financi[èe]res",
    "fcf": r"free cash ?flows?|\bfcff?\b",
    "dividend_per_share": r"dividends? per (?:ordinary )?share|\bdps\b|dividend of|dividende par action",
    "shares": r"(?:number of )?(?:ordinary )?shares (?:in issue|outstanding|issued)|issued share capital|"
              r"weighted average number",
}
_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december"]


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().rstrip(".")


def _on(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def source_standing(url: str, company_website: Optional[str] = None) -> str:
    """"official" (exchange or regulator), "company" (the company's own site), or "other"."""
    host = _host(url)
    if not host:
        return "other"
    if any(_on(host, d) for d in OFFICIAL_DOMAINS):
        return "official"
    site = _host(company_website if "//" in (company_website or "") else f"https://{company_website or ''}")
    site = site[4:] if site.startswith("www.") else site
    if site and _on(host, site):
        return "company"
    return "other"


def _safe(url: str) -> bool:
    p = urlparse(url)
    host = _host(url)
    if p.scheme not in ("https", "http") or not host or p.username or p.password:
        return False
    if host in {"localhost", "metadata.google.internal"} or host.endswith((".localhost", ".local", ".internal")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


def fetch_text(url: str, client: Optional[httpx.Client] = None) -> tuple[Optional[str], str]:
    """(document text, status) for a public PDF or web page; redirects are followed only to public hosts."""
    own = client is None
    c = client or httpx.Client(timeout=15, follow_redirects=False,
                               headers={"User-Agent": "Mozilla/5.0 (compatible; DealIntelligenceEvidence/1.0)"})
    try:
        current = url
        for _ in range(5):
            if not _safe(current):
                return None, "blocked"
            with c.stream("GET", current) as r:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    current = urljoin(current, r.headers["location"])
                    continue
                if r.status_code != 200:
                    return None, f"http_{r.status_code}"
                body = b""
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        return None, "too_large"
                kind = r.headers.get("content-type", "")
            if "pdf" in kind or body[:5] == b"%PDF-":
                from src.engines.financials import _pdf_text
                return _pdf_text(body, max_pages=80), "ok"
            text = body.decode("utf-8", errors="ignore")
            text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
            return html_mod.unescape(re.sub(r"<[^>]+>", " ", text)), "ok"
        return None, "too_many_redirects"
    except (httpx.HTTPError, ValueError) as e:
        return None, f"unreachable: {type(e).__name__}"
    finally:
        if own:
            c.close()


def _number_forms(value: float) -> list[str]:
    """How a figure can be written in a filing: in units, thousands, millions or billions, with or without
    thousands separators and decimals."""
    forms = set()
    v = abs(value)
    for div in (1, 1e3, 1e6, 1e9):
        x = v / div
        if x < 1:
            continue
        for digits in (0, 1, 2):
            r = round(x, digits)
            if digits and r == round(x):
                continue
            s = f"{r:,.{digits}f}"
            forms.update({s, s.replace(",", ""), s.replace(",", " "), s.replace(",", ".") if digits == 0 else s})
    return sorted(forms, key=len, reverse=True)


def figure_in_text(value: Optional[float], text: str) -> Optional[str]:
    """The form in which the figure appears in the text, or None."""
    if value is None or not text:
        return None
    flat = re.sub(r"[   ]+", " ", text)
    for form in _number_forms(value):
        if len(form.replace(",", "").replace(".", "").replace(" ", "")) < 3:
            continue                                    # "12" is everywhere
        if re.search(r"(?<![\d.,])" + re.escape(form) + r"(?![\d]|[.,]\d)", flat):
            return form
    return None


def labelled_figure(value: Optional[float], text: str, label: str) -> Optional[str]:
    """The form in which the figure appears on a line carrying its label (or the line after it, where a PDF
    breaks a row), or None. A figure found only elsewhere in the document does not count."""
    if value is None or not text:
        return None
    lines = [re.sub(r"[ \u00a0\u202f]+", " ", ln) for ln in text.splitlines()]
    pattern = re.compile(label, re.I)
    for i, line in enumerate(lines):
        if pattern.search(line):
            window = line + " " + (lines[i + 1] if i + 1 < len(lines) else "")
            form = figure_in_text(value, window)
            if form:
                return form
    return None


def statement_in_text(text: str) -> Optional[dict]:
    """The cited document read as a financial statement (line items, current and prior columns, accounting
    checks), when it is one."""
    from src.engines import financials as fin
    try:
        parsed = fin.parse_statement_text(text or "")
    except Exception:
        return None
    if len(parsed.get("items") or {}) < 2:
        return None
    mult = parsed.get("multiplier") or 1
    items = {k: {**v, "current": v["current"] * (1 if k == "eps" else mult)} for k, v in parsed["items"].items()}
    checks = fin.verify(parsed["items"])
    return {"items": items, "checks": checks, "verified": bool(checks) and all(c["passed"] for c in checks),
            "source": "parsed from the cited document"}


def _period_in_text(period: str, text: str) -> bool:
    try:
        d = date.fromisoformat(period[:10])
    except ValueError:
        return False
    low = text.lower()
    return str(d.year) in low and (_MONTHS[d.month - 1] in low or f"{d.day:02d}/{d.month:02d}/{d.year}" in low
                                   or d.isoformat() in low or f"{d.day} {_MONTHS[d.month - 1][:3]}" in low)


def _name_in_text(company: str, text: str) -> bool:
    words = [w for w in re.findall(r"[a-z0-9]+", company.lower())
             if w not in {"plc", "ltd", "limited", "group", "holdings", "company", "the", "share", "s", "a"} and len(w) > 2]
    low = text.lower()
    return bool(words) and all(w in low for w in words[:2])


def _close(a: float, b: float, tol: float) -> bool:
    return b != 0 and abs(a / b - 1) <= tol


def _age(day: Optional[str], today: date) -> Optional[int]:
    try:
        return (today - date.fromisoformat(str(day)[:10])).days
    except (TypeError, ValueError):
        return None


def check(inputs: dict, listing: Optional[dict] = None, filing: Optional[dict] = None,
          company_website: Optional[str] = None, fetch: Optional[Callable[[str], tuple[Optional[str], str]]] = None,
          today: Optional[date] = None) -> dict:
    """Evidence for each valuation input (see the module docstring). `inputs` holds company, currency, period,
    source, price, price_date, price_source, shares, and the method's figures (fcf, cash, debt or
    dividend_per_share); `listing` is the company's snapshot quote; `filing` the profile's parsed financials."""
    today = today or date.today()
    fetch = fetch or fetch_text
    fields: dict[str, dict] = {}
    method = inputs.get("method") or "dcf"
    wanted = ("fcf", "cash", "debt") if method == "dcf" else ("dividend_per_share",)

    # Source document.
    source = (inputs.get("source") or "").strip()
    standing = source_standing(source, company_website) if source else None
    text, fetched = (fetch(source) if source else (None, "missing"))
    doc = {"url": source or None, "standing": standing, "status": fetched,
           "names_company": bool(text) and _name_in_text(inputs.get("company") or "", text),
           "states_period": bool(text) and bool(inputs.get("period")) and _period_in_text(inputs["period"], text)}
    same_filing = bool(filing and filing.get("source_url") and source and filing["source_url"] == source)

    # The cited document read as a statement, when the profile has no parsed filing for this source.
    statement = filing if same_filing else (statement_in_text(text) if text else None)
    for key in wanted:
        value = inputs.get(key)
        if value is None:
            fields[key] = {"status": "unchecked", "note": "not entered"}
            continue
        parsed = None
        if statement:
            for item in _FIELDS[key]:
                cur = ((statement.get("items") or {}).get(item) or {}).get("current")
                if isinstance(cur, (int, float)):
                    parsed = cur
                    break
        if parsed is not None:
            ok = _close(value, parsed, FILING_TOLERANCE)
            where = "the filing" if same_filing else "the cited statement"
            fields[key] = {"status": "verified" if ok else "mismatch", "reference": parsed,
                           "note": ("matches" if ok else "differs from") + f" the current-period line in {where}"
                                   + (" (accounting checks passed)" if statement.get("verified") else "")}
            continue
        form = labelled_figure(value, text or "", _LABELS[key])
        if form:
            fields[key] = {"status": "found" if standing in ("official", "company") else "found_unofficial",
                           "note": f"appears as {form} on the document's {key.replace('_', ' ')} line"}
        elif figure_in_text(value, text or ""):
            fields[key] = {"status": "found_unlabelled",
                           "note": "the number appears in the document, but not on a line labelled as this item"}
        else:
            fields[key] = {"status": "not_found" if text else "unchecked",
                           "note": "not found in the cited document" if text else f"document could not be read ({fetched})"}

    # Price, currency, shares: the exchange's own data.
    price, price_date = inputs.get("price"), inputs.get("price_date")
    if price is None:
        fields["price"] = {"status": "unchecked", "note": "no price entered; no cheap/expensive verdict"}
    elif listing and listing.get("price"):
        ok = _close(price, listing["price"], PRICE_TOLERANCE)
        gap = _age(price_date, date.fromisoformat(listing["date"])) if listing.get("date") and price_date else None
        fields["price"] = {"status": "verified" if ok and (gap is None or abs(gap) <= 3) else "mismatch",
                           "reference": listing["price"], "reference_date": listing.get("date"),
                           "note": f"{listing['exchange_name']} close {listing['price']} {listing['currency']} on "
                                   f"{listing.get('date')}" + ("" if ok else "; the entered price differs")}
    else:
        form = figure_in_text(price, fetch(inputs["price_source"])[0] or "") if inputs.get("price_source") else None
        fields["price"] = {"status": "found" if form else "unchecked",
                           "note": "appears in the cited quote source" if form else "no exchange close to check against"}
    if listing:
        cur_ok = (inputs.get("currency") or "").upper() == listing.get("currency")
        fields["currency"] = {"status": "verified" if cur_ok else "mismatch", "reference": listing.get("currency"),
                              "note": f"the listing trades in {listing.get('currency')}"}
        shares = inputs.get("shares")
        if shares is not None and listing.get("shares"):
            ok = _close(shares, listing["shares"], SHARES_TOLERANCE)
            fields["shares"] = {"status": "verified" if ok else "mismatch", "reference": listing["shares"],
                                "note": "exchange-published shares outstanding" + ("" if ok else "; the entered count differs by more than 5%")}
    if "shares" not in fields and method == "dcf":
        form = labelled_figure(inputs.get("shares"), text or "", _LABELS["shares"])
        fields["shares"] = {"status": "found" if form else "unchecked",
                            "note": "appears in the cited document" if form else "no published share count to check against"}

    period_age, price_age = _age(inputs.get("period"), today), _age(price_date, today)
    fresh = {"statement_age_days": period_age, "statement_stale": period_age is not None and period_age > STATEMENT_MAX_AGE_DAYS,
             "price_age_days": price_age, "price_stale": price_age is not None and price_age > PRICE_MAX_AGE_DAYS}

    statement_ok = all(fields[k]["status"] in ("verified", "found") for k in wanted)
    mismatched = [k for k, f in fields.items() if f["status"] == "mismatch"]
    verdict_allowed = (statement_ok and fields["price"]["status"] in ("verified", "found") and not mismatched
                       and not fresh["statement_stale"] and not fresh["price_stale"])
    grade = ("A" if verdict_allowed and all(fields[k]["status"] == "verified" for k in (*wanted, "price")) else
             "B" if verdict_allowed else "C" if not mismatched and any(f["status"] in ("verified", "found") for f in fields.values())
             else "D")
    reasons = []
    if mismatched:
        reasons.append("Inputs that disagree with the evidence: " + ", ".join(mismatched) + ".")
    if not statement_ok:
        reasons.append("Not every statement figure was found in the filing or the cited document.")
    if fields["price"]["status"] not in ("verified", "found"):
        reasons.append("The price is not checked against an exchange close or the cited source.")
    if fresh["statement_stale"]:
        reasons.append("The statement period is more than 18 months old.")
    if fresh["price_stale"]:
        reasons.append("The price is more than a week old.")
    if standing == "other" and not same_filing:
        reasons.append("The source is neither an exchange or regulator filing nor the company's own site.")
    if any(f["status"] == "found_unlabelled" for f in fields.values()):
        reasons.append("Some figures appear in the document but not under their line item; they are not counted.")
    doc["read_as_statement"] = bool(statement) and not same_filing
    return {"grade": grade, "verdict_allowed": verdict_allowed, "fields": fields, "document": doc,
            "freshness": fresh, "reasons": reasons,
            "method": "Grade A: every figure matches exchange data or the current-period line of a parsed filing (the profile's, or "
                      "the cited document read as a statement). B: figures found on their labelled lines in an official "
                      "document and the price matches the exchange close (or the cited quote). C: partly evidenced. "
                      "D: unevidenced or contradicted. A cheap or expensive verdict needs A or B."}
