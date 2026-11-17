"""
Official records about a company, from bodies that publish them for their own reasons: competition authorities
clearing a merger, development-finance institutions disclosing an investment, debt markets publishing an issuer's
offering documents. Each record is dated and links to the publisher's own document, so a private company with no
press coverage still has verified facts.

records_for() merges every source into one newest-first list:
  {"kind", "authority", "title", "date", "url", "amount_usd"?, "instrument"?, "detail"?}
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


def merger_records(company: str, ticker: Optional[str] = None) -> list[dict]:
    from src.engines import merger_filings
    out = []
    for e in merger_filings.events_for(company, ticker):
        source = e.get("source") or ""
        authority, _, title = source.partition(" merger filing: ")
        out.append({"kind": "merger_filing", "authority": authority or "Competition authority",
                    "title": title.replace("-", " ").strip() or "Merger filing", "date": e.get("date"),
                    "url": e.get("url")})
    return out


def dfi_records(company: str, ticker: Optional[str] = None) -> list[dict]:
    from src.engines import dfi_disclosures
    return dfi_disclosures.records_for(company, ticker)


SOURCES = (merger_records, dfi_records)


def records_for(company: str, ticker: Optional[str] = None, limit: int = 20) -> list[dict]:
    """Every official record naming the company, newest first; a source that fails is left out."""
    out: list[dict] = []
    for source in SOURCES:
        try:
            out.extend(source(company, ticker))
        except Exception as e:                          # one source's failure never empties the others
            log.info("official records source %s failed: %r", source.__name__, e)
    seen, unique = set(), []
    for r in sorted(out, key=lambda r: r.get("date") or "", reverse=True):
        key = (r.get("kind"), r.get("url") or r.get("title"))
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique[:limit]
