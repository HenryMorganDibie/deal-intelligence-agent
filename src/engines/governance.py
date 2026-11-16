"""
Governance facts from a company's filed annual financial statements: the board (with roles), board committees,
substantial shareholders, subsidiaries, and the corporate details (registration number, registered office,
company secretary, auditor, registrar, holding company).

Annual statements lay these out differently from one company to the next, so the relevant pages are found by their
headings and a language model reads them into fields. Nothing it returns is shown unless it can be found on the page
it cites: every name must appear there word for word, and every percentage as written. A fact that fails the check
is dropped, not corrected, so a misread table cannot put a wrong shareholder on a profile.
"""
from __future__ import annotations

import io
import json
import logging
import re
import time
from typing import Callable, Optional

log = logging.getLogger(__name__)

MAX_PAGES = 600                 # every page: notes on subsidiaries sit deep in long reports (GTCO's runs to 336)
_MAX_PROMPT_CHARS = 26000

_SECTIONS = {
    "corporate": re.compile(r"(?i)corporate\s+information|registered\s+office|company\s+secretary|\bRC\s*(no|number)\b|"
                            r"registered\s+company\s+number|si[eè]ge\s+social|commissaires?\s+aux\s+comptes|\bRCCM\b|"
                            r"secr[ée]taire\s+(g[ée]n[ée]ral|du\s+conseil)"),
    "board": re.compile(r"(?i)board\s+of\s+directors|directors\W{0,3}\s+(report|profile)|composition\s+of\s+the\s+board|"
                        r"directors\s+who\s+served|directors\s+and\s+(professional\s+)?advisers|"
                        r"directors\s+and\s+(other\s+)?corporate\s+information|^\s*directors\s*$|"
                        r"our\s+board|board\s+and\s+management|directors\s+and\s+management|"
                        r"(non-?\s?executive|executive|independent)\s+directors|conseil\s+d.administration|administrateurs"),
    "committees": re.compile(r"(?i)(audit|risk|remuneration|nomination|governance)[\w ,&]{0,30}\s+committee|"
                             r"comit[ée]\s+(d.audit|des?\s+\w+)"),
    "shareholders": re.compile(r"(?i)substantial\s+(interest|shareholding)|major\s+shareholders|holding\s+(5|five)\s*%|"
                               r"shareholding\s+(analysis|structure)|analysis\s+of\s+shareholding|analysis\s+of\s+shareholders|"
                               r"shareholder\s+spread|top\s+\d+\s+shareholders|actionnariat|r[ée]partition\s+du\s+capital|"
                               r"principaux\s+actionnaires|"
                               r"(5|five)\s*%\s+(and\s+above|or\s+more)|more\s+than\s+(5|five)\s*%"),
    "subsidiaries": re.compile(r"(?i)(investments?\s+in|list\s+of|principal)\s+subsidiar|subsidiar(y|ies)\s+(undertakings|companies)|"
                               r"filiales"),
}
_PER_SECTION = {"corporate": 3, "board": 4, "committees": 3, "shareholders": 3, "subsidiaries": 4}
# Each group is read in its own pass with its own budget, so one long section cannot crowd out another.
GROUPS = (("corporate",), ("board",), ("committees",), ("shareholders",), ("subsidiaries",))
_ROLE = re.compile(r"(?i)\b(chairman|chairperson|non-executive|independent|executive director|managing director|"
                   r"chief executive|director|administrat(eur|rice)|pr[ée]sident(e)?|directeur\s+g[ée]n[ée]ral)\b")

SYSTEM = ("You read pages of a company's audited annual financial statements and return governance facts as JSON. "
          "Copy every name, title and figure exactly as printed. Never infer, translate or complete a value; leave out "
          "anything the pages do not state. Each list item must give the page number it was read from (the [p N] tag).")

USER = """Pages from the {company} annual financial statements ({document}):

{pages}

Return one JSON object with these keys (omit a key, or use an empty list, when the pages do not state it):
"rc_number": registration number as printed (e.g. "RC 208767"), with "rc_page";
"registered_office": the registered office address, with "office_page";
"company_secretary", "auditor", "registrar", "holding_company": names as printed, each with its own page
("company_secretary_page", "auditor_page", "registrar_page", "holding_company_page");
"board": [{{"name", "role" (e.g. "Chairman", "Independent Non-Executive Director", "Chief Executive Officer"), "nationality" if stated, "page"}}];
"committees": [{{"name", "members": [names], "page"}}];
"shareholders": [{{"name", "percent" (as printed, e.g. "86.65"), "page"}}] for holders of 5% or more;
"subsidiaries": [{{"name", "country" if stated, "percent" (ownership, as printed) if stated, "page"}}].
{focus}Return only the JSON object."""


def page_texts(data: bytes, max_pages: int = MAX_PAGES) -> list[str]:
    """Each page's text. PDFium reads a 236-page report in about a second (pypdf takes ten); pypdf remains the
    fallback when PDFium is not installed or cannot open the file."""
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(data)
        try:
            out = []
            for i in range(min(len(doc), max_pages)):
                try:
                    out.append(doc[i].get_textpage().get_text_range().replace("\r\n", "\n").replace("\r", "\n"))
                except Exception:
                    out.append("")
            return out
        finally:
            doc.close()
    except Exception:
        pass
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    out = []
    for p in reader.pages[:max_pages]:
        try:
            out.append(p.extract_text() or "")
        except Exception:
            out.append("")
    return out


OCR_MAX_PAGES = 220
VISION_PAGES = 12                         # pages of a scan transcribed on the spot (within free-tier rate limits)
VISION_PDF_BYTES = 18 * 1024 * 1024       # a scan sent whole to locate its sections (Gemini's inline limit is 20 MB)


def _png(width: int, height: int, gray: bytes, stride: int) -> bytes:
    """A grayscale PNG from raw 8-bit rows, with the standard library only (no imaging package needed)."""
    import struct
    import zlib
    raw = b"".join(b"\x00" + gray[y * stride:y * stride + width] for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _page_png(doc, i: int, scale: float = 2.0) -> bytes:
    bitmap = doc[i].render(scale=scale, grayscale=True)
    return _png(bitmap.width, bitmap.height, bytes(bitmap.buffer), bitmap.stride)


def _locate_sections(data: bytes, n_pages: int) -> list[int]:
    """1-based pages of a scanned report that hold the governance sections, from Gemini reading the whole PDF;
    the first pages when the file is too large to send or no page list comes back."""
    import base64
    from src.agents.signal_agent import gemini_vision
    pages: list[int] = []
    if len(data) <= VISION_PDF_BYTES:
        prompt = ("This is a company's annual report. Return only a JSON object mapping each of these sections to "
                  "the PDF page numbers (1-based position in this file, not the printed page numbers) where it "
                  "appears: corporate_information (registered office, company secretary, auditors, registrars), "
                  "board_of_directors (list or profiles of directors), committees, shareholders (shareholding "
                  "analysis, holders of 5% or more), subsidiaries. Use empty lists for sections not present.")
        try:
            raw = _json(gemini_vision([{"inline_data": {"mime_type": "application/pdf",
                                                         "data": base64.b64encode(data).decode()}},
                                       {"text": prompt}], max_tokens=2000))
            for key in ("corporate_information", "board_of_directors", "shareholders", "committees", "subsidiaries"):
                for v in raw.get(key) or []:
                    n = _page_number(v)
                    if isinstance(n, int) and 1 <= n <= n_pages:
                        for m in (n, n + 1):    # a list often runs onto the next page
                            if m <= n_pages and m not in pages:
                                pages.append(m)
        except Exception as e:
            log.warning("governance: locating sections in a scan failed: %s", e)
    if not pages:
        pages = list(range(1, min(n_pages, VISION_PAGES) + 1))
    return pages[:VISION_PAGES]


def vision_pages(data: bytes) -> Optional[list[str]]:
    """Text of a scanned report's governance pages, transcribed by Gemini from page images on the spot; the other
    pages are left empty. None when no Gemini key is set or nothing could be transcribed."""
    import base64
    import os
    if not os.getenv("GEMINI_API_KEY"):
        return None
    import pypdfium2 as pdfium
    from src.agents.signal_agent import gemini_vision
    doc = pdfium.PdfDocument(data)
    try:
        n = len(doc)
        wanted = _locate_sections(data, n)
        images = {p: _page_png(doc, p - 1) for p in wanted}
    finally:
        doc.close()
    prompt = ("Transcribe all the text on this page of a company's annual report exactly as printed, line by line, "
              "including tables (one row per line). Output only the text.")

    retry = ("List every line of text visible on this page image, in reading order, one per line, including names, "
             "titles, addresses and table rows with their figures.")

    def read(p: int) -> tuple[int, str]:
        image = {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(images[p]).decode()}}
        for text in (prompt, retry):          # a model can decline to copy text verbatim; ask again differently
            try:
                return p, gemini_vision([image, {"text": text}], max_tokens=6000)
            except Exception as e:
                log.warning("governance: transcribing page %s failed: %s", p, e)
        return p, ""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        texts = dict(pool.map(read, wanted))
    if not any(t.strip() for t in texts.values()):
        return None
    return [texts.get(i + 1, "") for i in range(n)]


def is_scanned(pages: list[str]) -> bool:
    """A PDF of page images: almost no text on its pages (a text PDF carries hundreds of characters a page)."""
    return bool(pages) and sum(len(t.strip()) for t in pages) / len(pages) < 120


def ocr_pages(data: bytes, max_pages: int = OCR_MAX_PAGES, dpi: int = 150) -> list[str]:
    """Page text from a scanned PDF by optical character recognition (Poppler's pdftoppm and Tesseract, both
    open source). Used by the scheduled job, where both are installed; an empty list where they are not."""
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path
    if not (shutil.which("pdftoppm") and shutil.which("tesseract")):
        return []
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "doc.pdf"
        pdf.write_bytes(data)
        subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-png", "-l", str(max_pages), str(pdf), f"{tmp}/p"],
                       check=True, timeout=900, capture_output=True)
        out = []
        for img in sorted(Path(tmp).glob("p-*.png"), key=lambda f: int(f.stem.split("-")[-1])):
            r = subprocess.run(["tesseract", str(img), "-", "--psm", "3"], capture_output=True, timeout=120)
            out.append(r.stdout.decode("utf-8", "ignore"))
            img.unlink()
        return out


_PCT = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d{1,3})?\s?%")
_PRIORITY = ("corporate", "shareholders", "board", "subsidiaries", "committees")
_PAGE_CHARS = 8000              # a full board or subsidiaries page (Dangote's run to 7,800 characters)


_ENTITY_WORDS = {"plc", "limited", "ltd", "group", "holding", "holdings", "company", "the", "of", "and", "co", "sa",
                 "inc", "pty", "proprietary", "nigeria", "kenya", "bank"}


def _other_board(text: str, company: Optional[str]) -> bool:
    """The page heads the board of another named entity ("Board of Directors - GTBank Limited") that does not share
    a distinctive word with the company: a subsidiary's board."""
    # The entity named on the heading's own line ("Board of Directors - GTBank Limited"), never the next line: a
    # heading "BOARD OF DIRECTORS:" followed by a director's name on its own line is the company's board.
    m = re.search(r"(?im)^[ \t]*board[ \t]+of[ \t]+directors[ \t]*[-–—:][ \t]*([^\n]{3,80})$", text or "")
    if not m or not company:
        return bool(m and re.search(r"(?i)\b(limited|ltd|plc|bank|s\.?a\.?)\b", m.group(1)) and not company)
    theirs = {w for w in re.findall(r"[a-z0-9]+", m.group(1).lower()) if w not in _ENTITY_WORDS}
    ours = {w for w in re.findall(r"[a-z0-9]+", company.lower()) if w not in _ENTITY_WORDS}
    # The company's own board is headed with its own name; any other word ("Fund Managers", "GTBank") is another
    # entity, a subsidiary, even when it shares the group name (Guaranty Trust Fund Managers Limited).
    words = re.findall(r"[a-z0-9]+", company.lower())
    return bool(theirs) and not all(w in ours or _abbreviates(w, words) for w in theirs)


def _abbreviates(token: str, words: list[str]) -> bool:
    """The token is built from the starts of the company's words, in order, some words skipped: "gtco" from
    Guaranty Trust (Holding) Company. "gtbank" is not: no word of the name starts with "bank"."""
    if len(token) < 3:
        return False

    def match(t: str, i: int, used: int) -> bool:
        if not t:
            return used >= 2
        for j in range(i, len(words)):
            for k in range(min(len(t), len(words[j])), 0, -1):
                if words[j][:k] == t[:k] and match(t[k:], j + 1, used + 1):
                    return True
        return False
    return match(token, 0, 0)


def _score(key: str, text: str, company: Optional[str] = None) -> float:
    """How strongly a page looks like the place a kind of fact is set out, 0 when it is not."""
    if _is_contents(text):
        return 0
    if key == "subsidiaries":
        # The list of subsidiaries carries an ownership percentage on every row; pages that only mention them
        # (the auditor's report, five-year summaries) carry none.
        n = len(_PCT.findall(text))
        return n if re.search(r"(?i)subsidiar|filiale", text) and n >= 3 else 0
    if key == "board" and _other_board(text, company):
        return 0                        # "Board of Directors - GTBank Limited": a subsidiary's board, not the company's
    if not _SECTIONS[key].search(text):
        return 0
    if key == "board":                  # a list of directors names many people next to their roles
        # A compact list (one director a line, role at the end) is the whole board on one page: it outranks
        # profile pages, which name fewer directors in more words.
        listed = len(re.findall(r"(?im)^[^\n]{3,80}?\b(chairman|chairperson|director|chief executive officer)\s*\**\s*$", text))
        # Profile pages print each director's role on its own line under the name (Naspers: "Independent
        # non-executive director"): several such lines are a run of board profiles.
        roles = len(re.findall(r"(?im)^\s*(lead\s+)?(independent\s+)?(non-?\s?executive\s+|executive\s+)?"
                               r"(chair(man|person)?|director|chief\s+executive)[\w ,&-]{0,40}$", text))
        return 1 + len(_ROLE.findall(text)) + (2 * listed if listed >= 6 else 0) + (2 * roles if roles >= 4 else 0)
    if key == "corporate":
        score = 1 + sum(bool(re.search(p, text, re.I)) for p in (r"registered\s+office", r"auditor", r"registrar",
                                                                   r"company\s+secretary", r"\bRC\b|company\s+number"))
        if re.search(r"(?i)corporate\s+information|registration\s+information|company\s+information|"
                     r"professional\s+advisers|statutory\s+information", text):
            score += 6                  # the page itself, not one that mentions the registrar in passing
        if re.search(r"(?i)notice\s+of\s+(the\s+)?annual\s+general\s+meeting|\bprox(y|ies)\b", text):
            score -= 4                  # AGM notices and proxy forms name the registrar and auditor too
        return max(score, 0)
    if key == "shareholders":
        return 1 + len(_PCT.findall(text))
    return 1 + len(re.findall(r"(?i)committee", text))


def section_pages(pages: list[str], key: str, company: Optional[str] = None) -> list[int]:
    """1-based numbers of the pages most likely to set out one kind of fact, best first. For shareholders and the
    corporate details the page after each one found is read too: a table often runs on past its heading's page."""
    scored = sorted(((_score(key, t, company), i + 1) for i, t in enumerate(pages)), key=lambda x: (-x[0], x[1]))
    best = [n for sc, n in scored if sc > 0][:_PER_SECTION[key]]
    if key == "board":
        own_heading = re.compile(r"(?im)^\s*(board\s+of\s+directors|our\s+board|directors)\b")
        best = [n for n in best if not (n > 1 and _other_board(pages[n - 2], company)
                                        and not own_heading.search(pages[n - 1]))]
        # Board profiles often run over two pages ("Non-executive directors" after the chairman's page).
        out = []
        for n in best:
            for m in (n, n + 1):
                if m <= len(pages) and m not in out and (m == n or (len(_ROLE.findall(pages[m - 1])) >= 4
                                                                   and not _other_board(pages[m - 1], company))):
                    out.append(m)
        return out[:_PER_SECTION[key] + 2]
    if key not in ("shareholders", "corporate"):
        return best
    out: list[int] = []
    for n in best:
        for m in (n, n + 1):
            if m <= len(pages) and m not in out and not _is_contents(pages[m - 1]):
                out.append(m)
    return out[:_PER_SECTION[key] * 2]


def select_pages(pages: list[str]) -> list[int]:
    """Every page chosen for any kind of fact, most important kind first."""
    chosen: list[int] = []
    for key in _PRIORITY:
        for n in section_pages(pages, key):
            if n not in chosen:
                chosen.append(n)
    return chosen


def _is_contents(text: str) -> bool:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    numbered = sum(1 for ln in lines if re.search(r"\s\d{1,3}\s*$", ln))
    return bool(re.search(r"(?i)\bcontents\b", text)) and numbered >= max(6, len(lines) // 2)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9%.]+", " ", (s or "").lower()).strip()


def _name_on_page(name: str, page: str) -> bool:
    """Every word of the name (of two letters or more, titles aside) appears on the page."""
    words = [w for w in _norm(name).split() if len(w) > 1 and w not in {"mr", "mrs", "ms", "dr", "chief", "alhaji", "prof"}]
    hay = f" {_norm(page)} "
    return bool(words) and all(f" {w} " in hay or f" {w}." in hay for w in words)


_GENERIC_HOLDER = re.compile(r"(?i)^\s*(the\s+)?((general|other|foreign|local|retail|institutional|individual|minority)\s+)*"
                             r"(public|investors?|shareholders?|others?|free\s+float|minorit(y|ies)|individuals?)"
                             r"(\s+(investors?|shareholders?|holders?))?\s*$|"
                             r"^\s*((institutionnels?|fonds|flottant|personnel|salari[ée]s|divers|autres|actionnaires|"
                             r"investisseurs|et|le|la|les|du|des|grand|public)\s*[,&]?\s*)+$")
_TITLES = {"mr", "mrs", "ms", "dr", "chief", "alhaji", "prof", "sir", "dame", "amb", "engr", "monsieur", "madame",
           "mademoiselle", "mme", "mlle", "me"}


def _phrase(s: str) -> str:
    s = re.sub(r"-\s*\n\s*", "-", s or "")          # a name broken across lines at a hyphen
    words = [w for w in re.sub(r"[^a-z0-9]+", " ", s.lower()).split() if w not in _TITLES]
    return " ".join(words)


def _phrase_on_page(value: str, page: str) -> bool:
    """The value appears on the page as printed: its words together and in order, not merely each somewhere on the
    page ("Deloitte & Touche South Africa (Deloitte)" is not on a page that prints "Deloitte & Touche")."""
    v = _phrase(value)
    return bool(v) and f" {v} " in f" {_phrase(page)} "


def _clean(value: str) -> str:
    """A value as printed, without page tags the model copied from the prompt ([p 150])."""
    return " ".join(re.sub(r"\[\s*p\.?\s*\d+\s*\]", " ", value or "").split()).strip(" ,;")


def _percent_on_page(percent, page: str) -> bool:
    if percent in (None, ""):
        return True
    p = str(percent).replace("%", "").strip()
    return bool(re.fullmatch(r"\d{1,3}(\.\d+)?", p)) and re.search(rf"(?<![\d.]){re.escape(p)}(?![\d])", page) is not None


def _percent_near(name: str, percent, page: str, lines_after: int) -> bool:
    """The percentage is printed beside the name: on the line where the name is (or ends, for a name broken across
    lines) or within `lines_after` lines below it, not merely somewhere on the page (an ownership diagram prints
    "100%" many times)."""
    words = [w for w in re.findall(r"[A-Za-z0-9]+", name or "") if w.lower() not in _TITLES]
    if not words or percent in (None, ""):
        return False
    p = str(percent).replace("%", "").strip()
    pattern = r"\W+".join(re.escape(w) for w in words)
    num = rf"(?<![\d.]){re.escape(p)}(?![\d])"
    for m in re.finditer(pattern, page or "", re.I):
        start = page.rfind("\n", 0, m.start()) + 1
        if lines_after == 0:
            # A subsidiary: its own table row (the figure after the name, on the line where the name ends) or a
            # label line with one figure only ("43.42% Prosus N.V."). "100% 100% 100% OXL" is ambiguous.
            end = page.find("\n", m.end())
            end = len(page) if end < 0 else end
            if re.search(num, page[m.end():end]):
                return True
            lines = page[start:end]
            if re.search(num, lines) and len(_PCT.findall(lines)) == 1:
                return True
            continue
        window = page[start:].split("\n")[:lines_after + 1 + m.group(0).count("\n")]
        if re.search(num, "\n".join(window)):
            return True
    return False


def _page(pages: list[str], n) -> Optional[str]:
    return pages[n - 1] if isinstance(n, int) and 1 <= n <= len(pages) else None


def _page_number(v):
    """A page number as the model wrote it ("92", 92.0, "p 92", "p92", "[p 92]") as an int; anything else unchanged."""
    if isinstance(v, bool):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        m = re.fullmatch(r"\s*\[?\s*(?:p(?:age)?\.?\s*)?(\d{1,4})\s*\]?\s*", v, re.I)
        return int(m.group(1)) if m else v
    return v


_SCALAR_FACTS = ("rc_number", "registered_office", "company_secretary", "auditor", "registrar", "holding_company")


def _normalise_pages(raw: dict) -> dict:
    raw = dict(raw)
    for k in _SCALAR_FACTS:             # {"name": "KPMG", "page": 102} as well as "KPMG" with "auditor_page"
        v = raw.get(k)
        if isinstance(v, dict):
            raw[k] = next((v[f] for f in ("name", "value", "address", "number", "text") if isinstance(v.get(f), str)), None)
            if v.get("page") is not None:
                page_key = {"rc_number": "rc_page", "registered_office": "office_page"}.get(k, f"{k}_page")
                raw.setdefault(page_key, v["page"])
    out = {}
    for k, v in raw.items():
        if k.endswith("_page"):
            out[k] = _page_number(v)
        elif isinstance(v, list):
            out[k] = [_normalise_item(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out


_NAME_KEYS = ("name", "shareholder", "holder", "director", "subsidiary", "company", "committee", "entity")
_PCT_KEYS = ("percent", "percentage", "holding", "shareholding", "ownership", "stake", "interest")


def _normalise_item(item: dict) -> dict:
    """A list entry as the checker expects it, whatever the model called its fields and however it wrote them:
    page tags removed from text ("86.65 [p 102]"), the percentage as the number printed, the page as a number."""
    out = dict(item)
    if not isinstance(out.get("name"), str):
        out["name"] = next((item[k] for k in _NAME_KEYS if isinstance(item.get(k), str)), None)
    if out.get("percent") in (None, ""):
        out["percent"] = next((item[k] for k in _PCT_KEYS if item.get(k) not in (None, "")), None)
    for k in ("name", "role", "country", "nationality"):
        if isinstance(out.get(k), str):
            out[k] = _clean(out[k])
    pct = out.get("percent")
    if isinstance(pct, str):
        m = re.search(r"\d{1,3}(?:\.\d+)?", _clean(pct))
        out["percent"] = m.group(0) if m else None
    if isinstance(out.get("members"), list):
        out["members"] = [_clean(m) for m in out["members"] if isinstance(m, str)]
    out["page"] = _page_number(item.get("page"))
    return out


def verify(raw: dict, pages: list[str], allowed: list[int]) -> dict:
    """Only the facts found on the page they cite (one of the pages that were read)."""
    raw = _normalise_pages(raw if isinstance(raw, dict) else {})
    ok = lambda n: n in allowed and _page(pages, n) is not None         # noqa: E731
    out: dict = {}
    rc = _clean(str(raw.get("rc_number") or ""))
    digits = re.sub(r"\D", "", rc)
    if 4 <= len(digits) <= 14:
        # a whole printed number, plain (208767) or in a slash format (1925/001431/06)
        has = lambda t: any(re.sub(r"\D", "", tok) == digits for tok in re.findall(r"\d[\d/]*\d|\d", t))  # noqa: E731
        if (ok(raw.get("rc_page")) and has(_page(pages, raw["rc_page"]))) or \
                [n for n in allowed if _page(pages, n) is not None and has(_page(pages, n))]:
            printed = re.search(r"\d[\d/]*\d", rc)                 # as printed: 208767, 1925/001431/06
            out["rc_number"] = printed.group(0) if printed else digits
    def find(cited, test, section: Optional[str] = None) -> Optional[int]:
        """The page the fact is on: the one cited when it is there; else a page read that has it (a model can cite a
        report's printed page number instead of the [p N] tag): the only one, or, when several do, the one that
        looks most like the section the fact belongs to."""
        if ok(cited) and test(_page(pages, cited)):
            return cited
        hits = [n for n in allowed if _page(pages, n) is not None and test(_page(pages, n))]
        if len(hits) == 1:
            return hits[0]
        if hits and section:
            ranked = sorted(hits, key=lambda n: -_score(section, _page(pages, n)))
            if _score(section, _page(pages, ranked[0])) > _score(section, _page(pages, ranked[1])):
                return ranked[0]
        return None

    office = _clean(raw["registered_office"]) if isinstance(raw.get("registered_office"), str) else None
    if office:
        words = [w for w in _norm(office).split() if len(w) > 2]
        if words and find(raw.get("office_page"), lambda t: sum(w in _norm(t) for w in words) >= 0.8 * len(words),
                          "corporate"):
            out["registered_office"] = " ".join(office.split())
    for key in ("company_secretary", "auditor", "registrar", "holding_company"):
        v = _clean(raw[key]) if isinstance(raw.get(key), str) else ""
        if v and find(raw.get(f"{key}_page", raw.get("corporate_page")), lambda t, v=v: _phrase_on_page(v, t),
                      "corporate"):
            out[key] = v
    board = []
    for b in raw.get("board") or []:
        if not (isinstance(b, dict) and isinstance(b.get("name"), str)):
            continue
        name = _clean(b["name"])
        n = find(b.get("page"), lambda t, name=name: _phrase_on_page(name, t), "board")
        if not n:
            continue
        text = _page(pages, n)
        item = {"name": name, "page": n}
        role = b.get("role")
        if isinstance(role, str) and role.strip() and _name_on_page(role, text):
            item["role"] = " ".join(role.split())
        if isinstance(b.get("nationality"), str) and _name_on_page(b["nationality"], text):
            item["nationality"] = b["nationality"].strip()
        if departed(name, text):
            continue
        if item["name"].lower() not in {x["name"].lower() for x in board}:
            board.append(item)
    if board:
        out["board"] = board
    committees = []
    for c in raw.get("committees") or []:
        if not (isinstance(c, dict) and isinstance(c.get("name"), str)):
            continue
        n = find(c.get("page"), lambda t, c=c: _name_on_page(c["name"], t))
        if not n:
            continue
        members = [" ".join(m.split()) for m in c.get("members") or []
                   if isinstance(m, str) and _name_on_page(m, _page(pages, n))]
        # A committee named on its page is kept even when that page does not list its members (an overview of
        # the board's committees); members are only those found on the same page.
        committees.append({"name": _clean(c["name"]), "members": members, "page": n})
    if committees:
        out["committees"] = committees
    for key in ("shareholders", "subsidiaries"):
        rows = []
        for r in raw.get(key) or []:
            if not (isinstance(r, dict) and isinstance(r.get("name"), str)):
                continue
            pct = r.get("percent")
            near = 10 if key == "shareholders" else 0     # a shareholder table may print names above the figures
            n = find(r.get("page"), lambda t, r=r, pct=pct, near=near: _name_on_page(r["name"], t) and
                     (pct in (None, "") or _percent_near(r["name"], pct, t, near)), key)
            if not n and key == "subsidiaries" and pct not in (None, ""):
                # The subsidiary is on the page but its percentage is not beside it (a diagram): keep the name only.
                pct = None
                n = find(r.get("page"), lambda t, r=r: _name_on_page(r["name"], t), key)
            if not n:
                continue
            if key == "shareholders" and (pct in (None, "") or float(str(pct).replace("%", "")) < 5):
                continue
            if key == "shareholders" and _GENERIC_HOLDER.search(r["name"]):
                continue                        # "public investors", "free float": a category, not a shareholder
            item = {"name": " ".join(r["name"].split()), "page": n}
            if pct not in (None, ""):
                item["percent"] = float(str(pct).replace("%", ""))
            if key == "subsidiaries" and isinstance(r.get("country"), str) and _name_on_page(r["country"], _page(pages, n)):
                item["country"] = r["country"].strip()
            if item["name"].lower() not in {x["name"].lower() for x in rows}:
                rows.append(item)
        if rows:
            out[key] = rows
    return out


def _json(text: str) -> dict:
    """The model's JSON object. An answer cut off by the output limit (a long subsidiaries list) keeps every item
    completed before the cut instead of being discarded."""
    start = (text or "").find("{")
    if start < 0:
        return {}
    body = text[start:]
    m = re.search(r"\{.*\}", body, re.S)
    if m:
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass
    return _repair_truncated(body)


def _repair_truncated(body: str) -> dict:
    """Close a JSON object cut off mid-answer at the last point where a value was complete."""
    stack: list[str] = []
    in_str = esc = False
    cuts: list[tuple[int, str]] = []          # (end index, closers) after each completed value
    for i, ch in enumerate(body):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if not stack:
                break
            stack.pop()
            if not stack:
                cuts.append((i + 1, ""))
                break
            cuts.append((i + 1, "".join(reversed(stack))))
    for end, closers in reversed(cuts):
        try:
            data = json.loads(body[:end] + closers)
        except json.JSONDecodeError:
            continue
        return data if isinstance(data, dict) else {}
    return {}


_SECTION_OF = {**dict.fromkeys(("rc_number", "registered_office", "company_secretary", "auditor", "registrar",
                                 "holding_company"), "corporate"),
               "board": "board", "committees": "committees", "shareholders": "shareholders", "subsidiaries": "subsidiaries"}


def extract(data: bytes, company: str, document: str, source_url: str, filed: Optional[str] = None,
            call: Optional[Callable[[str, str], str]] = None,
            source_label: str = "Annual financial statements filed with the exchange",
            allow_ocr: bool = False) -> Optional[dict]:
    """Governance facts from one annual statement PDF, each with the page it was read from; None when nothing on
    the pages could be confirmed. `call(system, user)` returns the model's text (the cached LLM by default)."""
    try:
        pages = page_texts(data)
    except Exception as e:
        log.warning("governance: %s unreadable: %s", source_url, e)
        return None
    ocr = False
    if is_scanned(pages):
        # A scan: its governance pages are transcribed by Gemini on the spot; Tesseract remains where it is installed.
        vision = vision_pages(data) if call is None else None
        if vision:
            pages, ocr = vision, True
        elif allow_ocr:
            try:
                pages, ocr = ocr_pages(data), True
            except Exception as e:
                log.warning("governance: OCR of %s failed: %s", source_url, e)
                return None
            if not pages:
                return None
        else:
            return None
    callers = [call] if call is not None else _default_calls()
    if not callers:
        return None
    from concurrent.futures import ThreadPoolExecutor

    def run(group: tuple) -> tuple[tuple, dict, list[int]]:
        chosen: list[int] = []
        for key in group:
            chosen += [n for n in section_pages(pages, key, company) if n not in chosen]
        if not chosen:
            return group, {}, []
        blocks, used = [], []
        for n in chosen:                # best pages first, each trimmed, within this pass's budget
            block = f"[p {n}]\n{pages[n - 1].strip()[:_PAGE_CHARS]}\n"
            if sum(len(b) for b in blocks) + len(block) > _MAX_PROMPT_CHARS:
                continue
            blocks.append(block)
            used.append(n)
        order = sorted(range(len(used)), key=lambda i: used[i])
        blocks, used = [blocks[i] for i in order], [used[i] for i in order]
        prompt = USER.format(company=company, document=document, pages="\n".join(blocks), focus=_FOCUS[group])

        def read(c) -> Optional[dict]:
            try:
                raw = _json(c(SYSTEM, prompt))
            except Exception as e:
                log.warning("governance: extraction failed for %s (%s): %s", source_url, "/".join(group), e)
                return None
            found = verify(raw, pages, used)
            log.info("governance: %s pass %s read pages %s; returned %s; confirmed %s", document, "/".join(group),
                     used, sorted(k for k, v in raw.items() if v), sorted(found))
            return found
        with ThreadPoolExecutor(max_workers=len(callers)) as readers:
            reads = list(readers.map(read, callers))
        if all(r is None for r in reads):        # every model failed (rate limit, outage): one more try
            time.sleep(5)
            reads = [read(callers[0])]
        reads = [r for r in reads if r]
        if group == ("board",):
            # Directors the page layout shows, each confirmed on its page and not marked as departed: a check that
            # does not depend on the model (both models can skip the same name).
            layout = [{"name": nm, "page": n} for n in used for nm in board_from_layout(pages[n - 1])
                      if not departed(nm, pages[n - 1])]
            if layout:
                reads.append({"board": layout})
        return group, combine_reads(reads), used

    # The passes are independent: run together, a report takes as long as its slowest pass, not their sum.
    with ThreadPoolExecutor(max_workers=len(GROUPS)) as pool:
        results = list(pool.map(run, GROUPS))
    facts: dict = {}
    used_all: list[int] = []
    for group, found, used in results:   # in GROUPS order, so the outcome does not depend on timing
        for k, v in found.items():      # a fact from the pass made for it wins over one found in passing
            if k not in facts or _SECTION_OF.get(k) in group:
                facts[k] = v
        used_all += [n for n in used if n not in used_all]
    if not facts:
        return None
    if facts.get("board"):
        facts["board"] = dedupe_board(facts["board"])
    if facts.get("shareholders") and facts.get("subsidiaries"):
        # A company's own subsidiary is not its shareholder (a group chart lists both).
        owned = {_key(r.get("name")) for r in facts["subsidiaries"]}
        facts["shareholders"] = [r for r in facts["shareholders"] if _key(r.get("name")) not in owned]
        if not facts["shareholders"]:
            del facts["shareholders"]
    used = sorted(used_all)
    if ocr:
        facts["ocr"] = True
    return {**facts, "source": f"{source_label}: {document}", "checker": CHECKER,
            "source_url": source_url, "filed": filed, "pages_read": used,
            "method": "Read from the report; each fact appears on the page cited, names and percentages "
                      "as printed. Facts that could not be found on their page are left out."}


_FOCUS = {
    ("corporate",): "In this pass give only rc_number, registered_office, company_secretary, auditor, registrar and "
                    "holding_company (with their pages).\n",
    ("board",): "In this pass give only board: every current director of this company's own board (not the boards of "
                "its subsidiaries), leaving out anyone marked as retired, resigned or deceased, and not skipping anyone "
                "listed after them.\n",
    ("committees",): "In this pass give only committees, with their members.\n",
    ("shareholders",): "In this pass give only shareholders: every holder of 5% or more of this company's own shares "
                       "(not the shareholders of its subsidiaries or associates) named in the text or in a table on "
                       "these pages, with the latest percentage shown.\n",
    ("subsidiaries",): "In this pass give only subsidiaries, every one listed, keeping each item short; where a table "
                       "shows two years, give the latest year's percentage.\n",
}


_LISTS = ("board", "committees", "shareholders", "subsidiaries")
# The version of the checks a stored read passed. Reads checked more loosely (a percentage anywhere on the page, a
# name's words anywhere on it) are not carried into a new read.
CHECKER = 2
_INITIALS = re.compile(r"^(?:[A-Z]{1,4}\.?\s*)+$")


def dedupe_board(board: list) -> list:
    """One entry per director. A report may print a director by initials in one place ("JP Bekker") and by name in
    another ("Koos Bekker"); the initials form is dropped when exactly one full name shares its surname."""
    def split(name: str) -> tuple[str, str]:
        parts = re.sub(r",.*$", "", str(name or "")).split()
        return (" ".join(parts[:-1]), parts[-1].lower()) if len(parts) > 1 else ("", (parts or [""])[0].lower())
    full: dict[str, int] = {}
    for d in board:
        given, surname = split(d.get("name") if isinstance(d, dict) else d)
        if given and not _INITIALS.match(given):
            full[surname] = full.get(surname, 0) + 1
    def words(name: str) -> set:
        return set(_phrase(re.sub(r",.*$", "", str(name or ""))).split())
    all_words = [words(d.get("name") if isinstance(d, dict) else d) for d in board]
    out, seen = [], set()
    for i, d in enumerate(board):
        name = d.get("name") if isinstance(d, dict) else d
        given, surname = split(name)
        if given and _INITIALS.match(given) and full.get(surname) == 1:
            continue
        mine = all_words[i]
        # A single word after titles ("DR. JAMES") is a fragment, not a director's name.
        if len(mine) < 2:
            continue
        whole = _phrase(str(name or ""))
        fulls = [_phrase(str(o.get("name") if isinstance(o, dict) else o)) for j, o in enumerate(board) if j != i]
        # A truncated copy of another entry ("Cabinet Secretary, The National" beside the full title).
        if any(o != whole and o.startswith(whole + " ") for o in fulls):
            continue
        # The same person with fewer initials ("C. Echeozo" beside "C. N. Echeozo"), titles aside.
        phrase = _phrase(re.sub(r",.*$", "", str(name or ""))).split()
        if len(phrase) >= 2 and all(len(w) == 1 for w in phrase[:-1]):
            others = [_phrase(re.sub(r",.*$", "", str(o.get("name") if isinstance(o, dict) else o))).split()
                      for j, o in enumerate(board) if j != i]
            mine_i = "".join(phrase[:-1])
            if any(len(o) > len(phrase) and o[-1] == phrase[-1] and all(len(w) == 1 for w in o[:-1])
                   and "".join(o[:-1]).startswith(mine_i) for o in others):
                continue
        key = re.sub(r"[^a-z0-9]", "", str(name).lower())
        if key and key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def merge_reads(new: Optional[dict], old: Optional[dict]) -> Optional[dict]:
    """Two reads of the same report: every fact confirmed in either is kept, and for a list the longer confirmed one.
    Free models vary from run to run; a weaker run must not erase what an earlier one confirmed on the page."""
    if not old or not new or old.get("source_url") != new.get("source_url") or old.get("checker") != CHECKER:
        return new or None
    out = dict(new)
    # Both reads passed the same checks on the same report, so every entry either confirmed is kept, once.
    lists = combine_reads([{k: new[k] for k in _LISTS if isinstance(new.get(k), list)},
                           {k: old[k] for k in _LISTS if isinstance(old.get(k), list)}])
    out.update(lists)
    for k, v in old.items():
        if k in _LISTS:
            continue
        elif k in _SCALAR_FACTS and v and not out.get(k):
            out[k] = v
            for pk in (k + "_page", "rc_page" if k == "rc_number" else "", "office_page" if k == "registered_office" else ""):
                if pk and old.get(pk) and not out.get(pk):
                    out[pk] = old[pk]
    out["pages_read"] = sorted(set(out.get("pages_read") or []) | set(old.get("pages_read") or []))
    return out


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _phrase(re.sub(r",.*$", "", name or "")))


def combine_reads(reads: list[dict]) -> dict:
    """Independent verified reads of the same pages: for each fact the first read's value, and for each list every
    entry either read confirmed (one per name, the one with more detail). Every entry has already been found on its
    page, so combining adds completeness without adding anything unconfirmed."""
    out: dict = {}
    for found in reads:
        for k, v in found.items():
            if k in _LISTS and isinstance(v, list):
                rows = {(_key(r.get("name")) or str(i)): r for i, r in enumerate(out.get(k) or [])}
                for r in v:
                    key = _key(r.get("name")) or f"new{len(rows)}"
                    if key not in rows or len(r.get("members") or []) > len(rows[key].get("members") or []):
                        rows[key] = r if key not in rows else {**rows[key], **r}
                out[k] = list(rows.values())
            elif k not in out:
                out[k] = v
    if out.get("board"):
        out["board"] = dedupe_board(out["board"])
    return out


_ROLE_LINE = re.compile(r"(?i)^\s*((lead\s+)?(senior\s+)?(deputy\s+)?(independent\s+)?(non-?\s?executive\s+|executive\s+)?"
                        r"(chair(man|person)?|vice[- ]chair(man|person)?|director|chief\s+executive(\s+officer)?|"
                        r"group\s+managing\s+director|managing\s+director)\b[\w ,&()-]{0,50}|"
                        r"(independent|non-?\s?executive|senior\s+deputy|deputy)(\s+non-?\s?executive)?\s*)$")
_NAME_LINE = re.compile(r"^(?:[A-Z][\w'’.-]+|de|du|da|dos|van|von|der|la|le|bin|al)(?:\s+(?:[A-Z][\w'’.-]+|de|du|da|dos|"
                        r"van|von|der|la|le|bin|al)){1,5}(?:,\s*[A-Z][\w.,\s]{1,20})?(?:\s+\d{2})?\**$")
_NOT_NAME = re.compile(r"(?i)\b(board|committee|report|date|appointment|expertise|contribution|directors?|management|"
                       r"company|limited|plc|group|annual|governance|chair|chairman|chairperson|chairwoman|executive|independent|"
                       r"officer|our|school|university|college|institute|foundation|association|council|ministry|"
                       r"commission|secretary|treasury)\b")


def board_from_layout(page: str) -> list[str]:
    """Directors read from the page's layout alone, as a check on the model: a line shaped like a person's name
    followed, within two lines, by a line that is a board role ("Independent non-executive director")."""
    lines = [ln.strip() for ln in (page or "").splitlines()]
    names = []
    for i, ln in enumerate(lines):
        ln = re.sub(r"\s+\d{2}\**$", "", ln)            # an age after the name ("Paul Cook 45")
        bare = re.sub(r",.*$", "", ln).replace("*", "").split()
        if not _NAME_LINE.match(ln) or _NOT_NAME.search(ln) or any(ch.isdigit() for ch in ln):
            continue                    # the whole line: "Ernest Ndukwe, OFR Nigerian Chairman" is not a bare name
        # Four or more words with no particle (de, van...) is two names on one line (a signature block).
        if len(bare) >= 4 and not any(w in {"de", "du", "da", "dos", "van", "von", "der", "la", "le", "bin", "al"}
                                      for w in bare):
            continue
        if any(_ROLE_LINE.match(nxt) for nxt in lines[i + 1:i + 4] if nxt):
            name = re.sub(r"\**$", "", ln).strip()
            if name not in names:
                names.append(name)
    return names


_GONE = re.compile(r"(?i)\b(retired|resigned|deceased|stepped\s+down|ceased\s+to\s+be)\b")


def departed(name: str, page: str) -> bool:
    """The page itself marks the director as no longer serving: "Deceased: 20 April 2026" in the lines after the name,
    or a footnote marker after the name ("Aliko Dangote, GCON*") whose note says retired or resigned."""
    m = re.search(re.escape(name.split(",")[0].strip()), page or "", re.I)
    if not m:
        return False
    after = page[m.end():m.end() + 400]
    marker = re.match(r"[^\n*]{0,40}?(\*+)", after)
    if marker:
        stars = re.escape(marker.group(1))
        note = re.search(rf"(?m)^\s*{stars}(?!\*)\s*([^\n]+)", page)
        if note and _GONE.search(note.group(1)) and not re.search(r"(?i)appointed", note.group(1)):
            return True
    # The lines of this director's own entry: up to the next line that starts another entry with a role.
    entry = re.split(r"\n(?=[A-Z][^\n]{2,60}\n[^\n]*(?:director|chair|executive))", after, maxsplit=1)[0][:300]
    return bool(re.search(r"(?im)^\s*(retired|resigned|deceased)\s*:", entry))


def _default_calls() -> list[Callable[[str, str], str]]:
    """The configured model chain, plus a second, different model reading the same pages at the same time when one
    is available (Gemini Flash-Lite): two independent reads miss less than one, at no extra wait."""
    try:
        from src.agents import signal_agent as sa
        client, provider = sa._get_llm_client()
    except Exception as e:
        log.info("governance: no language model configured: %s", e)
        return []
    # 8,000 tokens: room for reasoning models' thinking and a 45-row list.
    calls = [lambda system, user: sa._call_llm(client, provider, system, user, max_tokens=8000)]
    second = sa.second_opinion()
    if second:
        calls.append(lambda system, user: second(system, user, 8000))
    return calls


def _default_call() -> Optional[Callable[[str, str], str]]:
    calls = _default_calls()
    return calls[0] if calls else None
