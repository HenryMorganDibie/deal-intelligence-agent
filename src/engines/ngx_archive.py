"""
NGX's own daily price lists, from mid-2014: the exchange publishes a "Gainers and Price list for DD-MM-YYYY.zip" in
its public document library (doclib.ngxgroup.com, list DownloadsContent) for each trading day. Inside, PRICES1.pdf is
the official price list: every equity traded that day with its previous close, open, high, low, close, trades,
volume and value. The columns changed over the years (2020 added the official open and close), so each page is read
by its own header row.

Used by scripts/backfill_ngx_archive.py to fill NGX's daily history in public.price_history_years with official
closes (as published, not adjusted for later bonus issues or splits), in place of the third-party history.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date
from typing import Iterable, Optional

LIBRARY = "https://doclib.ngxgroup.com"
LIST_ITEMS = (LIBRARY + "/_api/Web/Lists/GetByTitle('DownloadsContent')/items?$select=FileRef&$top=5000")
SOURCE = "NGX daily price list"

_ZIP_REF = re.compile(r"/gainers and price list for (\d{1,2})-(\d{1,2})-(\d{4})\.zip$", re.I)
_TRADED_ON = re.compile(r"PRICES FOR EQUITY SECURITIES TRADED ON (\d{2})/(\d{2})/(\d{4})", re.I)
_HEADER = re.compile(r"^S/N\s+COMPANY\s+(.*)$", re.I)
_NUM = re.compile(r"^-?[\d,]+(?:\.\d+)?$")

# Tickers NGX has since changed, so old lists join the current listing.
RENAMES = {"GUARANTY": "GTCO", "ACCESS": "ACCESSCORP", "FBNH": "FIRSTHOLDCO", "STERLNBANK": "STERLINGNG"}


def zip_refs(file_refs: Iterable[str]) -> dict[date, str]:
    """{trading day: library path} for every daily price-list zip in the library's file list."""
    out: dict[date, str] = {}
    for ref in file_refs:
        m = _ZIP_REF.search(ref or "")
        if not m:
            continue
        try:
            day = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        out.setdefault(day, ref)
    return out


def _number(token: str) -> Optional[float]:
    return float(token.replace(",", "")) if _NUM.match(token) else None


def parse_price_text(text: str) -> tuple[Optional[date], dict[str, dict]]:
    """(trading day, {symbol: {close, volume, value}}) from the text of an NGX equity price list. Rows whose
    column count does not match the page's header are skipped rather than guessed."""
    day = None
    m = _TRADED_ON.search(text or "")
    if m:
        day = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    cols: list[str] = []
    out: dict[str, dict] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        h = _HEADER.match(line)
        if h:
            cols = h.group(1).upper().split()
            continue
        if not cols or "CLOSE" not in cols:
            continue
        tokens = line.split()
        if len(tokens) != len(cols) + 2 or not tokens[0].isdigit():
            continue
        symbol = tokens[1].upper()
        if not re.match(r"^[A-Z0-9][A-Z0-9.&-]{0,19}$", symbol):
            continue
        values = dict(zip(cols, tokens[2:]))
        close = _number(values["CLOSE"])
        if close is None or close <= 0:
            continue
        out[RENAMES.get(symbol, symbol)] = {"close": close, "volume": _number(values.get("VOLUME", "")),
                                            "value": _number(values.get("VALUE", ""))}
    return day, out


def parse_zip(content: bytes) -> tuple[Optional[date], dict[str, dict]]:
    """The equity price list inside one daily zip; (None, {}) when there is none."""
    import pypdfium2 as pdfium
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        return None, {}
    best: tuple[Optional[date], dict[str, dict]] = (None, {})
    for name in archive.namelist():
        if not name.lower().endswith(".pdf"):
            continue
        try:
            pdf = pdfium.PdfDocument(io.BytesIO(archive.read(name)))
            text = "\n".join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf)))
        except Exception:  # noqa: BLE001 - a damaged file is skipped, the day reported missing
            continue
        if not _TRADED_ON.search(text):
            continue
        day, rows = parse_price_text(text)
        if len(rows) > len(best[1]):
            best = (day, rows)
    return best
