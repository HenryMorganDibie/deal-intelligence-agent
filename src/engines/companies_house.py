"""
Accounts filed at UK Companies House, for African companies whose holding company is registered in the UK.

Many African startups are held by a UK company (it files accounts every year, and they are public). This module
finds the UK company by exact name, takes its latest accounts filing, and reads the machine-readable version
(inline XBRL, "iXBRL") into the same line items the exchange statements use: revenue, profit, assets, liabilities,
equity, cash. Every figure keeps the tag it was read from, and the usual accounting identities are checked.

Matching is deliberately strict: the UK company's name must equal the African company's name once legal suffixes
are removed ("Kuda Technologies Ltd" for "Kuda Technologies"), it must be active, and exactly one company may match.
Anything looser would show one company's accounts on another's profile.

The free Companies House API needs a key (HTTP Basic, the key as the user name): COMPANIES_HOUSE_API_KEY.
"""
from __future__ import annotations

import logging
import os
import re
from html import unescape
from typing import Optional

import httpx

log = logging.getLogger(__name__)

API = "https://api.company-information.service.gov.uk"

# iXBRL concept (local name, any taxonomy prefix) -> our line item. The first concept present wins.
CONCEPTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("revenue", ("TurnoverRevenue", "Turnover", "TurnoverGrossOperatingRevenue", "Revenue")),
    ("cost_of_sales", ("CostSales", "CostOfSales")),
    ("gross_profit", ("GrossProfitLoss", "GrossProfit")),
    ("operating_profit", ("OperatingProfitLoss", "OperatingProfit")),
    ("profit_before_tax", ("ProfitLossOnOrdinaryActivitiesBeforeTax", "ProfitLossBeforeTax")),
    ("income_tax", ("TaxTaxCreditOnProfitOrLossOnOrdinaryActivities", "IncomeTaxExpenseCredit")),
    ("profit_after_tax", ("ProfitLoss", "ProfitLossForPeriod")),
    ("total_assets", ("TotalAssets", "Assets")),
    ("total_liabilities", ("TotalLiabilities", "Liabilities")),
    ("total_equity", ("Equity", "NetAssetsLiabilities", "ShareholderFunds")),
    ("cash", ("CashBankOnHand", "CashCashEquivalents", "CashAtBankAndInHand")),
)
_SUFFIX = re.compile(r"(?i)\b(?:limited|ltd|plc|holdings?|group|inc|incorporated|llc|uk|co)\b\.?")


def _key(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", _SUFFIX.sub(" ", (name or "").lower()))).strip()


def _client(api_key: Optional[str] = None) -> Optional[httpx.Client]:
    key = api_key or os.environ.get("COMPANIES_HOUSE_API_KEY", "").strip()
    if not key:
        return None
    return httpx.Client(auth=(key, ""), timeout=20, follow_redirects=True,
                        headers={"User-Agent": "DealIntelligence/1.0 (+https://deal-intelligence.app)"})


def find_company(name: str, client: httpx.Client) -> Optional[dict]:
    """The one active UK company whose name equals ours without legal suffixes; None when none or several match."""
    want = _key(name)
    if len(want) < 3:
        return None
    r = client.get(f"{API}/search/companies", params={"q": name, "items_per_page": 20})
    if r.status_code != 200:
        return None
    hits = [i for i in r.json().get("items") or []
            if _key(i.get("title", "")) == want and (i.get("company_status") or "") == "active"]
    return hits[0] if len(hits) == 1 else None


def latest_accounts(number: str, client: httpx.Client) -> Optional[dict]:
    """The newest accounts filing that has a machine-readable (iXBRL) version, with its period end."""
    r = client.get(f"{API}/company/{number}/filing-history", params={"category": "accounts", "items_per_page": 10})
    if r.status_code != 200:
        return None
    for item in r.json().get("items") or []:
        meta_url = (item.get("links") or {}).get("document_metadata")
        if not meta_url:
            continue
        meta = client.get(meta_url)
        if meta.status_code != 200:
            continue
        resources = (meta.json().get("resources") or {})
        if "application/xhtml+xml" not in resources:
            continue                                  # a scanned or PDF-only filing: skip to an older one
        return {"date": item.get("date"), "period_end": item.get("action_date"),
                "kind": item.get("description"), "content_url": meta_url.rstrip("/") + "/content"}
    return None


def _contexts(doc: str) -> dict[str, str]:
    """contextRef -> the period's end date (or instant)."""
    out = {}
    for m in re.finditer(r'<xbrli:context[^>]*\bid="([^"]+)"(.*?)</xbrli:context>', doc, re.S):
        if re.search(r"<xbrli:segment|<xbrldi:", m.group(2)):
            continue                                  # a dimension (a class of shares, a segment): not the total
        end = re.search(r"<xbrli:(?:endDate|instant)>\s*([\d-]{10})", m.group(2))
        if end:
            out[m.group(1)] = end.group(1)
    return out


def _number(text: str, attrs: str) -> Optional[float]:
    raw = unescape(re.sub(r"<[^>]+>", "", text)).strip()
    if raw in ("", "-", "—", "–"):
        return 0.0
    if "numcommadecimal" in attrs:                    # 1.234,56
        raw = raw.replace(".", "").replace(",", ".")
    raw = raw.replace(",", "").replace(" ", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    scale = re.search(r'\bscale="(-?\d+)"', attrs)
    if scale:
        value *= 10 ** int(scale.group(1))
    if re.search(r'\bsign="-"', attrs):
        value = -value
    return value


def parse_ixbrl(doc: str) -> dict:
    """{"period": {...}, "items": {field: {"current", "prior", "line"}}} from an iXBRL accounts document."""
    contexts = _contexts(doc)
    facts: dict[str, dict[str, float]] = {}
    for m in re.finditer(r'<ix:nonFraction\b([^>]*)>(.*?)</ix:nonFraction>', doc, re.S | re.I):
        attrs, body = m.group(1), m.group(2)
        name = re.search(r'\bname="(?:[\w-]+:)?([\w-]+)"', attrs)
        ref = re.search(r'\bcontextRef="([^"]+)"', attrs)
        if not (name and ref and ref.group(1) in contexts):
            continue
        value = _number(body, attrs)
        if value is not None:
            facts.setdefault(name.group(1), {}).setdefault(contexts[ref.group(1)], value)
    ends = sorted({e for by_end in facts.values() for e in by_end}, reverse=True)
    if not ends:
        return {"period": None, "items": {}}
    current = ends[0]
    items: dict[str, dict] = {}
    for field, concepts in CONCEPTS:
        for concept in concepts:
            by_end = facts.get(concept)
            if by_end and current in by_end:
                prior_end = next((e for e in sorted(by_end, reverse=True) if e < current), None)
                items[field] = {"current": by_end[current], "prior": by_end.get(prior_end) if prior_end else None,
                                "line": f"iXBRL {concept}"}
                break
    return {"period": {"end": current, "months": None, "label": f"Period ended {current}"}, "items": items}


def accounts_for(name: str, api_key: Optional[str] = None, client: Optional[httpx.Client] = None) -> Optional[dict]:
    """The latest filed accounts of the UK company matching `name`, in the profile's financials shape; None if no
    unambiguous match, no machine-readable filing, or fewer than two line items."""
    from src.engines import financials
    own = client is None
    c = client or _client(api_key)
    if c is None:
        return None
    try:
        company = find_company(name, c)
        if not company:
            return None
        filing = latest_accounts(company["company_number"], c)
        if not filing:
            return None
        doc = c.get(filing["content_url"], headers={"Accept": "application/xhtml+xml"})
        if doc.status_code != 200:
            return None
        parsed = parse_ixbrl(doc.text)
    except (httpx.HTTPError, ValueError, KeyError) as e:
        log.info("companies house: %s unavailable: %s", name, e)
        return None
    finally:
        if own:
            c.close()
    items = {k: v for k, v in parsed["items"].items() if v.get("current") is not None}
    if len(items) < 2:
        return None
    checks = financials.verify(items)
    return {
        "company_name": company.get("title"), "company_number": company["company_number"],
        "period": parsed["period"], "currency": "GBP", "unit": "£", "multiplier": 1,
        "items": items, "checks": checks, "verified": bool(checks) and all(x["passed"] for x in checks),
        "status": financials.item_status(items, checks),
        "source_url": f"https://find-and-update.company-information.service.gov.uk/company/{company['company_number']}/filing-history",
        "filed": filing["date"], "accounts_type": filing["kind"],
        "basis": "Filed accounts of the UK company (company or group, as filed); figures in pounds",
    }


RECHECK_DAYS = 90


def refresh(directory: list[dict], limit: int = 150, pause: float = 0.6) -> dict:
    """Weekly: look up private companies (most deals first) at Companies House and store matched accounts with the
    company's website facts. A company checked in the last RECHECK_DAYS is skipped, matched or not."""
    import time
    from datetime import date, timedelta
    from src import company_web
    from src import hosted_market as hm
    c = _client()
    if c is None:
        return {"skipped": "COMPANIES_HOUSE_API_KEY not set"}
    if not hm._configured():
        return {"skipped": "database not configured"}
    cutoff = (date.today() - timedelta(days=RECHECK_DAYS)).isoformat()
    private = sorted((r for r in directory if r.get("kind") == "private"),
                     key=lambda r: -(r.get("deal_count") or 0))
    checked = matched = 0
    found: list[str] = []
    try:
        for r in private:
            if checked >= limit:
                break
            key = company_web.name_key(r["name"])
            got = hm._rpc_sync("company_web_get", {"p_name_key": key}, 10)
            row = got.json() if got.status_code == 200 and got.json() else None
            facts = dict((row or {}).get("facts") or {})
            if (facts.get("uk_checked_at") or "") >= cutoff:
                continue
            checked += 1
            accounts = accounts_for(r["name"], client=c)
            time.sleep(pause)                         # well inside the API's 600 requests per five minutes
            facts["uk_checked_at"] = date.today().isoformat()
            if accounts:
                facts["uk_accounts"] = accounts
                matched += 1
                found.append(f"{r['name']} -> {accounts['company_name']}")
            if not row:
                hm._rpc_sync("company_web_request", {"p_name_key": key, "p_name": r["name"], "p_website": None}, 10)
            hm._rpc_sync("company_web_save", {"p_name_key": key, "p_status": (row or {}).get("status") or "queued",
                                              "p_facts": facts, "p_error": (row or {}).get("error")}, 15)
    finally:
        c.close()
    return {"checked": checked, "matched": matched, "found": found}
