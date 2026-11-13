"""Parse INEC's 2027 final candidate lists (one PDF per state and office) into src/data/ng_candidates_2027.json.

    python scripts/parse_inec_candidates.py <folder of PDFs named gov__*, sen__*, reps__*> 

The PDFs carry a watermark ("INEC" in large green letters) whose characters land inside cells; they are filtered out
by size before reading. A governorship row holds the governor and deputy in one cell; names are split at the height
of the "Deputy" label.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "data" / "ng_candidates_2027.json"
OFFICE = {"gov": "governorship", "sen": "senate", "reps": "house_of_representatives"}


def _has_letters(text: str, word: str) -> bool:
    """The word's letters in order within text, allowing watermark letters between them ("EAGCE" has "AGE")."""
    return re.search(".*".join(word), text.upper()) is not None


def _clean_name(words: list[str]) -> str:
    kept = [w for w in words if not re.fullmatch(r"[A-Z]", w)]          # watermark letters; initials carry a dot
    return " ".join(kept).strip(" ,")


def _words_in(page, bbox) -> list[dict]:
    x0, top, x1, bottom = bbox
    return [w for w in page.crop((x0, top, x1, bottom)).extract_words(keep_blank_chars=False)]


def _lines(words: list[dict]) -> list[tuple[float, str]]:
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if rows and abs(rows[-1][0]["top"] - w["top"]) < 3:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [(r[0]["top"], " ".join(x["text"] for x in sorted(r, key=lambda w: w["x0"]))) for r in rows]


def parse(path: Path) -> list[dict]:
    kind = path.name.split("__")[0]
    out = []
    with pdfplumber.open(path) as pdf:
        header = None
        for raw_page in pdf.pages:
            # The watermark is "INEC" in green letters some 300 points high; its characters are dropped before reading.
            page = raw_page.filter(lambda o: not (o.get("object_type") == "char" and o.get("size", 0) > 40))
            for table in page.find_tables():
                for row in table.rows:
                    cells = [c for c in row.cells]
                    texts = [(page.crop(c).extract_text() or "").strip() if c else "" for c in cells]
                    if texts and texts[0].strip().endswith("SN") and len(texts) >= 8:
                        # Every list has the same column order; the watermark garbles header words ("GENCDER"),
                        # so columns are taken by position, the header only confirming it is the expected table.
                        if not (_has_letters(texts[4], "PARTY") and _has_letters(texts[6], "AGE")
                                and _has_letters(texts[7], "GENDER")):
                            raise ValueError(f"{path.name}: unexpected columns {texts}")
                        col = {"STATE": 1, "POSITION": 2, "CONSTITUENCY": 2, "NAME OF CANDIDATE": 3, "PARTY": 4,
                               "AGE": 6, "GENDER": 7, "REMARKS": len(texts) - 1}
                        header = texts
                        continue
                    if not header or not texts or not texts[0].strip().isdigit():
                        continue
                    state = texts[col["STATE"]].split("\n")[0].strip().title()
                    party = texts[col["PARTY"]].split("\n")[-1].strip()
                    ages = re.findall(r"\b\d{2}\b", texts[col["AGE"]])
                    genders = re.findall(r"\b[MF]\b", texts[col["GENDER"]])
                    name_cell = cells[col["NAME OF CANDIDATE"]]
                    remarks = " ".join(dict.fromkeys(texts[col["REMARKS"]].split())).title() or None   # "Court Order"
                    name_lines = _lines(_words_in(page, name_cell))
                    if kind == "gov":
                        pos_lines = _lines(_words_in(page, cells[col["POSITION"]]))
                        deputy_top = next((t for t, s in pos_lines if s.startswith("Deputy")), None)
                        gov = [s for t, s in name_lines if deputy_top is None or t < deputy_top - 2]
                        dep = [s for t, s in name_lines if deputy_top is not None and t >= deputy_top - 2]
                        out.append({"office": "governorship", "state": state, "constituency": state, "party": party,
                                    "name": _clean_name(" ".join(gov).split()).title(),
                                    "running_mate": _clean_name(" ".join(dep).split()).title() or None,
                                    "age": int(ages[0]) if ages else None, "gender": genders[0] if genders else None,
                                    "remarks": remarks})
                    else:
                        con = re.sub(r"\s*/\s*", "/", " ".join(texts[col["CONSTITUENCY"]].split())).title()
                        out.append({"office": OFFICE[kind], "state": state, "constituency": con, "party": party,
                                    "name": _clean_name(" ".join(s for _, s in name_lines).split()).title(),
                                    "age": int(ages[0]) if ages else None, "gender": genders[0] if genders else None,
                                    "remarks": remarks})
    return out


def main(folder: str) -> None:
    rows = []
    for path in sorted(Path(folder).glob("*__*.pdf")):
        got = parse(path)
        rows += got
        print(f"{path.name}: {len(got)}", file=sys.stderr)
    for r in rows:
        r["name"] = r["name"] or None                      # a ticket INEC lists without a name (court order)
        r["state"] = {"Fct": "FCT", "Federal Capital Territory": "FCT", "Akwa-Ibom": "Akwa Ibom", "Akwa": "Akwa Ibom", "Cross": "Cross River",
                      "Cross-River": "Cross River"}.get(r["state"], r["state"])
    OUT.write_text(json.dumps({"source": "INEC final lists of candidates, 2027 general elections (published October 2026)",
                               "candidates": rows}, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps({"candidates": len(rows), "by_office": {o: sum(1 for r in rows if r["office"] == o)
                                                              for o in OFFICE.values()}}))


if __name__ == "__main__":
    main(sys.argv[1])
