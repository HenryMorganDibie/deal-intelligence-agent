"""Strict URL-host verification for official African market disclosures.

A publisher name alone never makes a source official. Only HTTPS URLs whose hostname
matches a country or regional official-source allowlist can receive an official-host match.
The registry is deliberately explicit; missing host mappings remain unverified.
"""
from __future__ import annotations

from urllib.parse import urlparse
from src.data.africa_countries import countries_in_text, resolve as resolve_country

# Explicit publisher-domain registry. This means the domain is a known news outlet,
# not that the outlet is an official institution or that every article is accurate.
RECOGNISED_NEWS_HOSTS: tuple[str, ...] = (
    "nairametrics.com", "techcabal.com", "thisdaylive.com", "guardian.ng",
    "businessday.ng", "businessday.co.za", "moneyweb.co.za", "theafricareport.com",
    "disruptafrica.com", "techpoint.africa", "technext24.com", "businesslive.co.za",
    "theeastafrican.co.ke", "nation.africa", "standardmedia.co.ke", "citizen.digital",
    "dailytrust.com", "punchng.com", "vanguardngr.com", "premiumtimesng.com",
    "thecable.ng", "african.business", "financialafrik.com", "agenceecofin.com",
    "shega.co", "borkena.com", "reuters.com", "bloomberg.com",
    "ft.com", "apnews.com", "bbc.com", "bbc.co.uk",
)


def is_recognised_news_host(url: str | None) -> bool:
    """True only for HTTPS URLs on the explicit news-publisher host list."""
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return parsed.scheme.lower() == "https" and bool(host) and any(
        host == domain or host.endswith("." + domain) for domain in RECOGNISED_NEWS_HOSTS
    )


# Domains are allowlisted by institution/country; matching is exact or a true subdomain.
# The API reports host match, not a guarantee that every page's claims are correct.
OFFICIAL_HOSTS_BY_COUNTRY: dict[str, tuple[str, ...]] = {
    "DZ": ("bank-of-algeria.dz", "cosob.dz", "sgbv.dz"),
    "EG": ("cbe.org.eg", "fra.gov.eg", "egx.com.eg"),
    "LY": ("cbl.gov.ly",),
    "MA": ("bkam.ma", "casablanca-bourse.com", "ammc.ma"),
    "SD": ("cbos.gov.sd",),
    "TN": ("bct.gov.tn", "bvmt.com.tn", "cmf.tn"),
    "BJ": ("bceao.int", "brvm.org", "amf-umoa.org"),
    "BF": ("bceao.int", "brvm.org", "amf-umoa.org"),
    "CV": ("bcv.cv", "bolsacv.cv"),
    "CI": ("bceao.int", "brvm.org", "amf-umoa.org"),
    "GM": ("cbg.gm",),
    "GH": ("bog.gov.gh", "gse.com.gh", "sec.gov.gh"),
    "GN": ("bcrg-guinee.org",),
    "GW": ("bceao.int", "brvm.org", "amf-umoa.org"),
    "LR": ("cbl.org.lr",),
    "ML": ("bceao.int", "brvm.org", "amf-umoa.org"),
    "MR": ("bcm.mr",),
    "NE": ("bceao.int", "brvm.org", "amf-umoa.org"),
    "NG": ("cbn.gov.ng", "ngxgroup.com", "sec.gov.ng"),
    "SN": ("bceao.int", "brvm.org", "amf-umoa.org"),
    "SL": ("bsl.gov.sl",),
    "TG": ("bceao.int", "brvm.org", "amf-umoa.org"),
    "AO": ("bna.ao", "bodiva.ao", "cmc.ao"),
    "CM": ("beac.int", "bvm-ac.org", "cosumaf.org"),
    "CF": ("beac.int", "bvm-ac.org", "cosumaf.org"),
    "TD": ("beac.int", "bvm-ac.org", "cosumaf.org"),
    "CG": ("beac.int", "bvm-ac.org", "cosumaf.org"),
    "CD": ("bcc.cd",),
    "GQ": ("beac.int", "bvm-ac.org", "cosumaf.org"),
    "GA": ("beac.int", "bvm-ac.org", "cosumaf.org"),
    "ST": ("bcstp.st",),
    "BI": ("brb.bi",),
    "KM": ("banque-comores.km",),
    "DJ": ("banque-centrale.dj",),
    "ER": (),
    "ET": ("nbe.gov.et", "ecma.gov.et", "esx.et"),
    "KE": ("centralbank.go.ke", "nse.co.ke", "cma.or.ke"),
    "MG": ("banque-centrale.mg",),
    "MW": ("rbm.mw", "mse.mw"),
    "MU": ("bom.mu", "stockexchangeofmauritius.com", "fscmauritius.org"),
    "MZ": ("bancomoc.mz", "bvm.co.mz"),
    "RW": ("bnr.rw", "rse.rw", "cma.rw"),
    "SC": ("centralbank.sc", "fsa.sc", "merj.exchange"),
    "SO": ("centralbank.gov.so",),
    "SS": ("boss.gov.ss",),
    "TZ": ("bot.go.tz", "dse.co.tz", "cmsa.go.tz"),
    "UG": ("bou.or.ug", "use.or.ug", "cmauganda.co.ug"),
    "ZM": ("boz.zm", "luse.co.zm", "seczambia.org.zm"),
    "ZW": ("rbz.co.zw", "zse.co.zw", "seczim.co.zw"),
    "BW": ("bankofbotswana.bw", "bse.co.bw", "nbfira.org.bw"),
    "SZ": ("centralbank.org.sz", "eswatinistockexchange.co.sz", "fsra.co.sz"),
    "LS": ("centralbank.org.ls",),
    "NA": ("bon.com.na", "nsx.com.na", "namfisa.com.na"),
    "ZA": ("resbank.co.za", "jse.co.za", "fsca.co.za"),
}
REGIONAL_OFFICIAL_HOSTS: tuple[str, ...] = (
    "bceao.int", "brvm.org", "amf-umoa.org", "beac.int", "bvm-ac.org", "cosumaf.org",
    "afdb.org", "afreximbank.com", "ifc.org", "ebrd.com", "eib.org",
)
GLOBAL_OFFICIAL_HOSTS: tuple[str, ...] = ("sec.gov", "edgar.sec.gov", "worldbank.org", "imf.org")


def _host_matches(host: str, allowed: str) -> bool:
    host = host.lower().rstrip(".")
    allowed = allowed.lower().rstrip(".")
    return host == allowed or host.endswith("." + allowed)


def _iso2(value: str | None) -> str:
    country = resolve_country(country=value)
    return country.iso2 if country else (value or '').upper()


def verify_url(url: str | None, country_iso2: str | None = None) -> dict:
    """Return a reasoned official-host match; never infer official status from publisher text."""
    if not url:
        return {"status": "missing_url", "host": None, "matched_registry": None}
    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        host = ""
        parsed = None
    if not parsed or parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
        return {"status": "invalid_or_non_https_url", "host": host or None, "matched_registry": None}
    # Google News links are article wrappers, not the underlying publisher's host.
    # Do not call them invalid or infer the publisher from title/metadata. Resolving
    # them requires a separately bounded, cached ingestion-time resolver.
    if host == "news.google.com" or host.endswith(".news.google.com"):
        return {"status": "news_wrapper_unresolved", "host": host, "matched_registry": None}
    code = _iso2(country_iso2)
    candidates = [(d, "country") for d in OFFICIAL_HOSTS_BY_COUNTRY.get(code, ())]
    candidates += [(d, "regional") for d in REGIONAL_OFFICIAL_HOSTS]
    candidates += [(d, "global") for d in GLOBAL_OFFICIAL_HOSTS]
    for domain, registry in candidates:
        if _host_matches(host, domain):
            return {"status": "official_host_match", "host": host, "matched_registry": registry,
                    "matched_domain": domain}
    return {"status": "unverified_host", "host": host, "matched_registry": None}


def audit_country(country_iso2: str, deals: list[dict], events: list[dict]) -> dict:
    """Count official-host evidence and explicit source gaps across deal/event records."""
    code = _iso2(country_iso2)
    def record_country_codes(record: dict) -> set[str]:
        raw = ([record.get("country")] if record.get("country") else []) + (record.get("countries") or [])
        codes: set[str] = set()
        for value in raw:
            if isinstance(value, str) and len(value.strip()) == 2 and value.strip().isalpha():
                codes.add(value.strip().upper())
                continue
            resolved = resolve_country(country=value)
            if resolved:
                codes.add(resolved.iso2)
            elif isinstance(value, str):
                codes.update(country.iso2 for country in countries_in_text(value))
        return codes
    country_deals = [d for d in deals if code in record_country_codes(d)]
    country_events = [e for e in events if code in record_country_codes(e)]
    source_checks: list[dict] = []
    official_deal_ids: set[str] = set()
    official_event_ids: set[str] = set()
    missing_url = 0
    unverified_url = 0
    invalid_url = 0
    recognised_news_url = 0
    unresolved_wrapper_url = 0
    wrapper_with_publisher_host = 0

    def check_record(record: dict, record_kind: str) -> bool:
        nonlocal missing_url, unverified_url, invalid_url, recognised_news_url, unresolved_wrapper_url, wrapper_with_publisher_host
        sources = record.get("sources") or []
        if not sources:
            url = record.get("url") or record.get("source_url")
            publisher_url = record.get("publisher_url")
            if url or publisher_url:
                sources = [{
                    "url": url,
                    "publisher_url": publisher_url,
                    "publisher": record.get("publisher") or record.get("source"),
                }]
            else:
                missing_url += 1
                return False
        matched = False
        for source in sources:
            article_url = source.get("url")
            publisher_url = source.get("publisher_url")
            article_host = (urlparse(str(article_url)).hostname or "").lower() if article_url else ""
            is_google_wrapper = article_host == "news.google.com" or article_host.endswith(".news.google.com")
            # Google News RSS includes a separate <source url="..."> publisher
            # domain. Verify that domain instead of treating the wrapper as the
            # publisher; keep the wrapper URL for traceability.
            verification_url = publisher_url if (is_google_wrapper or not article_url) and publisher_url else article_url
            if is_google_wrapper and publisher_url:
                wrapper_with_publisher_host += 1
            result = verify_url(verification_url, code)
            if is_google_wrapper and not publisher_url:
                result = {**result, "status": "news_wrapper_unresolved", "host": article_host,
                          "publisher_host": None}
            else:
                result = {**result, "publisher_host": (urlparse(str(publisher_url)).hostname or "").lower()
                          if publisher_url else None}
            source_checks.append({
                **result,
                "publisher": source.get("publisher") or source.get("source"),
                "url": article_url,
                "publisher_url": publisher_url,
                "record_kind": record_kind,
            })
            if result["status"] == "official_host_match":
                matched = True
            elif result["status"] == "missing_url":
                missing_url += 1
            elif result["status"] == "invalid_or_non_https_url":
                invalid_url += 1
            elif result["status"] == "news_wrapper_unresolved":
                unresolved_wrapper_url += 1
            elif is_recognised_news_host(verification_url):
                recognised_news_url += 1
            else:
                unverified_url += 1
        return matched

    for deal in country_deals:
        if check_record(deal, "deal"):
            official_deal_ids.add(str(deal.get("id") or id(deal)))
    for event in country_events:
        if check_record(event, "event"):
            official_event_ids.add(str(event.get("id") or id(event)))

    official_hosts = list(OFFICIAL_HOSTS_BY_COUNTRY.get(code, ()))
    return {
        "country": code,
        "deal_records": len(country_deals),
        "event_records": len(country_events),
        "source_links_checked": len(source_checks),
        "official_host_matched_links": sum(1 for source in source_checks if source["status"] == "official_host_match"),
        "deal_records_with_official_host": len(official_deal_ids),
        "deal_records_without_official_host": max(0, len(country_deals) - len(official_deal_ids)),
        "event_records_with_official_host": len(official_event_ids),
        "event_records_without_official_host": max(0, len(country_events) - len(official_event_ids)),
        "records_without_source_url": missing_url,
        # Keep the legacy field for existing clients, but define it as valid HTTPS
        # hosts not present in the official registry. Invalid links and unresolved
        # Google News wrappers are reported separately instead of being conflated.
        "unverified_or_invalid_source_urls": unverified_url + invalid_url,
        "unverified_publisher_source_urls": unverified_url,
        "recognised_news_publisher_source_urls": recognised_news_url,
        "invalid_or_non_https_source_urls": invalid_url,
        "unresolved_news_wrapper_source_urls": unresolved_wrapper_url,
        "news_wrapper_publisher_hosts_checked": wrapper_with_publisher_host,
        "registered_country_hosts": len(official_hosts),
        "registry_status": "needs_host_review" if not official_hosts else "host_allowlist_configured",
        "verification_scope": "HTTPS hostname matched to an explicit country/regional/global official-institution allowlist. This verifies the publisher domain, not the transaction claim itself.",
    }
