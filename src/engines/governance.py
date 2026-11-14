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
from typing import Callable, Optional

log = logging.getLogger(__name__)

MAX_PAGES = 600                 # every page: notes on subsidiaries sit deep in long reports (GTCO's runs to 336)
_MAX_PROMPT_CHARS = 18000

_SECTIONS = {
    "corporate": re.compile(r"(?i)corporate\s+information|registered\s+office|company\s+secretary|\bRC\s*(no|number)\b|"
                            r"registered\s+company\s+number"),
    "board": re.compile(r"(?i)board\s+of\s+directors|directors\W{0,3}\s+(report|profile)|composition\s+of\s+the\s+board|"
                        r"directors\s+who\s+served"),
    "committees": re.compile(r"(?i)(audit|risk|remuneration|nomination|governance)[\w ,&]{0,30}\s+committee"),
    "shareholders": re.compile(r"(?i)substantial\s+(interest|shareholding)|major\s+shareholders|holding\s+(5|five)\s*%|"
                               r"shareholding\s+(analysis|structure)|analysis\s+of\s+shareholding|top\s+\d+\s+shareholders|"
                               r"(5|five)\s*%\s+(and\s+above|or\s+more)|more\s+than\s+(5|five)\s*%"),
    "subsidiaries": re.compile(r"(?i)(investments?\s+in|list\s+of|principal)\s+subsidiar|subsidiar(y|ies)\s+(undertakings|companies)"),
}
_PER_SECTION = {"corporate": 2, "board": 3, "committees": 3, "shareholders": 3, "subsidiaries": 4}
# Each group is read in its own pass with its own budget, so one long section cannot crowd out another.
GROUPS = (("corporate", "board", "committees"), ("shareholders",), ("subsidiaries",))
_ROLE = re.compile(r"(?i)\b(chairman|chairperson|non-executive|independent|executive director|managing director|"
                   r"chief executive|director)\b")

SYSTEM = ("You read pages of a company's audited annual financial statements and return governance facts as JSON. "
          "Copy every name, title and figure exactly as printed. Never infer, translate or complete a value; leave out "
          "anything the pages do not state. Each list item must give the page number it was read from (the [p N] tag).")

USER = """Pages from the {company} annual financial statements ({document}):

{pages}

Return one JSON object with these keys (omit a key, or use an empty list, when the pages do not state it):
"rc_number": registration number as printed (e.g. "RC 208767"), with "rc_page";
"registered_office": the registered office address, with "office_page";
"company_secretary", "auditor", "registrar", "holding_company": names as printed, with "corporate_page";
"board": [{{"name", "role" (e.g. "Chairman", "Independent Non-Executive Director", "Chief Executive Officer"), "nationality" if stated, "page"}}];
"committees": [{{"name", "members": [names], "page"}}];
"shareholders": [{{"name", "percent" (as printed, e.g. "86.65"), "page"}}] for holders of 5% or more;
"subsidiaries": [{{"name", "country" if stated, "percent" (ownership, as printed) if stated, "page"}}].
Return only the JSON object."""


def page_texts(data: bytes, max_pages: int = MAX_PAGES) -> list[str]:
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
_PAGE_CHARS = 3500


def _score(key: str, text: str) -> float:
    """How strongly a page looks like the place a kind of fact is set out, 0 when it is not."""
    if _is_contents(text):
        return 0
    if key == "subsidiaries":
        # The list of subsidiaries carries an ownership percentage on every row; pages that only mention them
        # (the auditor's report, five-year summaries) carry none.
        n = len(_PCT.findall(text))
        return n if re.search(r"(?i)subsidiar", text) and n >= 3 else 0
    if not _SECTIONS[key].search(text):
        return 0
    if key == "board":                  # a list of directors names many people next to their roles
        return 1 + len(_ROLE.findall(text))
    if key == "corporate":
        return 1 + sum(bool(re.search(p, text, re.I)) for p in (r"registered\s+office", r"auditor", r"registrar",
                                                                  r"company\s+secretary", r"\bRC\b|company\s+number"))
    if key == "shareholders":
        return 1 + len(_PCT.findall(text))
    return 1 + len(re.findall(r"(?i)committee", text))


def section_pages(pages: list[str], key: str) -> list[int]:
    """1-based numbers of the pages most likely to set out one kind of fact, best first."""
    scored = sorted(((_score(key, t), i + 1) for i, t in enumerate(pages)), key=lambda x: (-x[0], x[1]))
    return [n for sc, n in scored if sc > 0][:_PER_SECTION[key]]


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


def _percent_on_page(percent, page: str) -> bool:
    if percent in (None, ""):
        return True
    p = str(percent).replace("%", "").strip()
    return bool(re.fullmatch(r"\d{1,3}(\.\d+)?", p)) and re.search(rf"(?<![\d.]){re.escape(p)}(?![\d])", page) is not None


def _page(pages: list[str], n) -> Optional[str]:
    return pages[n - 1] if isinstance(n, int) and 1 <= n <= len(pages) else None


def _page_number(v):
    """A page number as the model wrote it ("92", 92.0, "p 92", "p92") as an int; anything else unchanged."""
    if isinstance(v, bool):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        m = re.fullmatch(r"\s*(?:p(?:age)?\.?\s*)?(\d{1,4})\s*", v, re.I)
        return int(m.group(1)) if m else v
    return v


def _normalise_pages(raw: dict) -> dict:
    out = {}
    for k, v in raw.items():
        if k.endswith("_page"):
            out[k] = _page_number(v)
        elif isinstance(v, list):
            out[k] = [{**i, "page": _page_number(i.get("page"))} if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out


def verify(raw: dict, pages: list[str], allowed: list[int]) -> dict:
    """Only the facts found on the page they cite (one of the pages that were read)."""
    raw = _normalise_pages(raw if isinstance(raw, dict) else {})
    ok = lambda n: n in allowed and _page(pages, n) is not None         # noqa: E731
    out: dict = {}
    rc = str(raw.get("rc_number") or "")
    digits = re.sub(r"\D", "", rc)
    if 4 <= len(digits) <= 9 and ok(raw.get("rc_page")) and digits in re.sub(r"\D", " ", _page(pages, raw["rc_page"])).split():
        out["rc_number"] = digits
    def find(cited, test) -> Optional[int]:
        """The page the fact is on: the one cited when it is there, else the only page read that has it (a model can
        cite a report's printed page number instead of the [p N] tag)."""
        if ok(cited) and test(_page(pages, cited)):
            return cited
        hits = [n for n in allowed if _page(pages, n) is not None and test(_page(pages, n))]
        return hits[0] if len(hits) == 1 else None

    office = raw.get("registered_office")
    if isinstance(office, str):
        words = [w for w in _norm(office).split() if len(w) > 2]
        if words and find(raw.get("office_page"), lambda t: sum(w in _norm(t) for w in words) >= 0.8 * len(words)):
            out["registered_office"] = " ".join(office.split())
    for key in ("company_secretary", "auditor", "registrar", "holding_company"):
        v = raw.get(key)
        if isinstance(v, str) and v.strip() and find(raw.get("corporate_page"), lambda t, v=v: _name_on_page(v, t)):
            out[key] = " ".join(v.split())
    board = []
    for b in raw.get("board") or []:
        if not (isinstance(b, dict) and isinstance(b.get("name"), str)):
            continue
        n = find(b.get("page"), lambda t, b=b: _name_on_page(b["name"], t))
        if not n:
            continue
        text = _page(pages, n)
        item = {"name": " ".join(b["name"].split()), "page": n}
        role = b.get("role")
        if isinstance(role, str) and role.strip() and _name_on_page(role, text):
            item["role"] = " ".join(role.split())
        if isinstance(b.get("nationality"), str) and _name_on_page(b["nationality"], text):
            item["nationality"] = b["nationality"].strip()
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
        if members:
            committees.append({"name": " ".join(c["name"].split()), "members": members, "page": n})
    if committees:
        out["committees"] = committees
    for key in ("shareholders", "subsidiaries"):
        rows = []
        for r in raw.get(key) or []:
            if not (isinstance(r, dict) and isinstance(r.get("name"), str)):
                continue
            pct = r.get("percent")
            n = find(r.get("page"), lambda t, r=r, pct=pct: _name_on_page(r["name"], t) and _percent_on_page(pct, t))
            if not n:
                continue
            if key == "shareholders" and (pct in (None, "") or float(str(pct).replace("%", "")) < 5):
                continue
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
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


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
        if not allow_ocr:
            return None
        try:
            pages, ocr = ocr_pages(data), True
        except Exception as e:
            log.warning("governance: OCR of %s failed: %s", source_url, e)
            return None
        if not pages:
            return None
    if call is None:
        call = _default_call()
        if call is None:
            return None
    facts: dict = {}
    used_all: list[int] = []
    for group in GROUPS:
        chosen: list[int] = []
        for key in group:
            chosen += [n for n in section_pages(pages, key) if n not in chosen]
        if not chosen:
            continue
        blocks, used = [], []
        for n in chosen:                # best pages first, each trimmed, within this pass's budget
            block = f"[p {n}]\n{pages[n - 1].strip()[:_PAGE_CHARS]}\n"
            if sum(len(b) for b in blocks) + len(block) > _MAX_PROMPT_CHARS:
                continue
            blocks.append(block)
            used.append(n)
        order = sorted(range(len(used)), key=lambda i: used[i])
        blocks, used = [blocks[i] for i in order], [used[i] for i in order]
        try:
            raw = _json(call(SYSTEM, USER.format(company=company, document=document, pages="\n".join(blocks))))
        except Exception as e:
            log.warning("governance: extraction failed for %s (%s): %s", source_url, "/".join(group), e)
            continue
        found = verify(raw, pages, used)
        log.info("governance: %s pass %s read pages %s; returned %s; confirmed %s", document, "/".join(group), used,
                 sorted(k for k, v in raw.items() if v), sorted(found))
        for k, v in found.items():      # a fact from the pass made for it wins over one found in passing
            if k not in facts or _SECTION_OF.get(k) in group:
                facts[k] = v
        used_all += [n for n in used if n not in used_all]
    if not facts:
        return None
    used = sorted(used_all)
    if ocr:
        facts["ocr"] = True
    return {**facts, "source": f"{source_label}: {document}",
            "source_url": source_url, "filed": filed, "pages_read": used,
            "method": "Read from the report; each fact appears on the page cited, names and percentages "
                      "as printed. Facts that could not be found on their page are left out."}


def _default_call() -> Optional[Callable[[str, str], str]]:
    try:
        from src.agents import signal_agent as sa
        client, provider = sa._get_llm_client()
    except Exception as e:
        log.info("governance: no language model configured: %s", e)
        return None
    return lambda system, user: sa._call_llm(client, provider, system, user, max_tokens=2500)
