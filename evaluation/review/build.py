"""
Draw a year's independent-review sample: headlines and report pairs for two human annotators.

    python -m evaluation.review.build --year 2027 --from-api https://deal-intelligence-api.vercel.app
    python -m evaluation.review.build --year 2026 --pool evaluation/review/2026/pool.jsonl --out /tmp/check

Each year gets its own folder, evaluation/review/<year>/. A year that already has a manifest is
never redrawn, so labels in progress are never overwritten (pass --out to rebuild elsewhere, e.g.
to check that a published draw reproduces). Item files carry the headline, publisher and date only,
never the system's extraction, so labels stay blind. The stratum of each item and the system's
merge decision for each pair go to separate files that annotators must not open. The seed is fixed
per year: re-running on the same pool gives the same sample.

Pool sources:
    --from-api URL       the hosted API's deals (with every source report) and deal-like events
    --from-export PATH   a raw store export (deals with sources, merge flags, events)
    --pool PATH          an existing pool.jsonl
"""
from __future__ import annotations

import json
import random
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

from src.engines import deals as dl

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
N_RANDOM, N_PER_HARD, N_NEGATIVE = 120, 15, 20
N_PAIR_MERGED, N_PAIR_LOOKALIKE, N_PAIR_HARD_NEGATIVE = 40, 40, 20
MIN_POOL_RECORDS = 200

_FRENCH = re.compile(r"(?i)\b(l[eè]ve|rach[eè]te|acquiert|c[eè]de|milliards?|financement|pr[eê]t|lev[ée]e|investit)\b")
_DEALISH = re.compile(r"(?i)(acquir|acquisition|merg|stake|invest|raises|raised|funding|financ|loan|facility|ipo|"
                      r"listing|fund |rach[eè]t|l[eè]ve|cession|financement)")
_GENERIC = {"capital", "africa", "african", "bank", "group", "holdings", "fund", "partners", "limited", "ventures",
            "energy", "power", "solar", "investment", "investments", "global", "international", "finance", "the",
            "south", "north", "east", "west", "central", "southern", "nigeria", "nigerian", "kenya", "kenyan", "egypt",
            "egyptian", "ghana", "morocco", "moroccan", "tanzania", "uganda", "rwanda", "senegal", "zambia", "zimbabwe",
            "ethiopia", "tunisia", "algeria", "angola", "cameroon", "ivoire", "coast", "francophone", "expansion"}

LABEL_FIELDS = {
    "is_transaction": None, "in_scope": None, "scope_reason": "", "deal_type": None, "stage": None, "target": None,
    "acquirer_or_lead": None, "other_parties": [], "amount": None, "currency": None, "amount_kind": None,
    "stake_pct": None, "country": None, "country_basis": None, "africa_wide": None, "asset_location": None,
    "language": None, "confidence": None, "note": "",
}
PAIR_FIELDS = {"same_transaction": None, "confidence": None, "note": ""}


def seed_for(year: int) -> int:
    return int(f"{year}1020")


def _key(title: str) -> str:
    return re.sub(r"\W+", " ", (title or "").lower()).strip()


def _words(name: str) -> set[str]:
    return {w for w in dl.normalise_name(name or "").split() if len(w) > 3 and w not in _GENERIC}


def _write_pool(rows: list[dict], out: Path, source: str) -> None:
    header = {"_pool": "independent review", "snapshot": date.today().isoformat(), "source": source, "rows": len(rows)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in [header, *rows]))
    print(f"pool: {len(rows)} headlines -> {out}")


def pool_from_export(export: Path, out: Path) -> None:
    """Flatten a raw store export (deals with their sources, deal-like events) into one row per headline."""
    raw = json.loads(export.read_text())
    if "result" in raw:                               # an export saved from the SQL tool wraps its JSON
        raw = json.loads(re.search(r">\s*(\[\{.*\}\])\s*</untrusted-data", raw["result"], re.S).group(1))[0]
        raw = next(iter(raw.values()))
    rows = []
    for d in raw["deals"] or []:
        for s in d.get("sources") or []:
            if s.get("t"):
                rows.append({"kind": "deal", "title": s["t"], "publisher": s.get("p"), "date": s.get("d"),
                             "url": s.get("u"), "record": d["rid"], "merged_into": d.get("merged_into"),
                             "excluded": d.get("excluded"), "deal_type": d.get("deal_type"), "usd": d.get("usd"),
                             "countries": d.get("nctry") or 0, "target": d.get("target")})
    for e in raw["events"] or []:
        if e.get("t"):
            rows.append({"kind": "event", "title": e["t"], "publisher": e.get("p"), "date": e.get("d"),
                         "url": e.get("u"), "excluded": e.get("excluded")})
    _write_pool(rows, out, "store export")


def _get(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "independent-review"}), timeout=60) as r:
        return json.loads(r.read())


def pool_from_api(api: str, year: int, out: Path) -> None:
    """One row per source report of every visible deal announced in the year, plus deal-like events.

    The public API shows merged duplicates folded into the record that absorbed them, so a record's
    several source reports are the reports the system merged.
    """
    api = api.rstrip("/")
    rows, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"since": f"{year}-01-01", "until": f"{year}-12-31", "limit": 100, "offset": offset})
        page = _get(f"{api}/api/deals?{q}")
        for d in page.get("deals") or []:
            for s in d.get("sources") or []:
                if s.get("title"):
                    rows.append({"kind": "deal", "title": s["title"], "publisher": s.get("publisher"),
                                 "date": s.get("date") or d.get("announced"), "url": s.get("url"), "record": d["id"],
                                 "merged_into": None, "excluded": False, "deal_type": d.get("deal_type"),
                                 "usd": d.get("amount_usd"), "countries": len(d.get("countries") or []),
                                 "target": d.get("target")})
        offset += 100
        if offset >= (page.get("total_matching") or 0) or not page.get("deals"):
            break
    offset = 0
    while True:
        page = _get(f"{api}/api/events?" + urllib.parse.urlencode({"since": f"{year}-01-01", "limit": 500, "offset": offset}))
        for e in page.get("events") or []:
            if (e.get("day") or "")[:4] == str(year) and _DEALISH.search(e.get("headline") or ""):
                rows.append({"kind": "event", "title": e["headline"], "publisher": e.get("publisher"),
                             "date": e.get("day"), "url": e.get("url"), "excluded": False})
        offset += 500
        if offset >= (page.get("count") or 0) or not page.get("events"):
            break
    _write_pool(rows, out, api)


def _previous_titles(year: int) -> set[str]:
    """Headlines already used by any earlier evaluation set or another year's review."""
    seen = set()
    paths = [*(ROOT / "evaluation" / "deals").glob("*_items.jsonl"), *(ROOT / "evaluation" / "attribution").glob("*_items.jsonl"),
             *(p for p in HERE.glob("*/items.jsonl") if p.parent.name != str(year)),
             *(p for p in HERE.glob("*/pairs.jsonl") if p.parent.name != str(year))]
    for path in paths:
        for line in path.open():
            item = json.loads(line)
            for t in (item.get("title"), (item.get("a") or {}).get("title") if isinstance(item.get("a"), dict) else None,
                      (item.get("b") or {}).get("title") if isinstance(item.get("b"), dict) else None):
                if t:
                    seen.add(_key(t))
    return seen


def _item(item_id: str, r: dict) -> dict:
    return {"item_id": item_id, "title": r["title"], "publisher": r.get("publisher"), "date": r.get("date")}


def build(year: int, pool_path: Path, out_dir: Path) -> dict:
    seed = seed_for(year)
    rng = random.Random(seed)
    lines = [json.loads(l) for l in pool_path.open()]
    rows = [r for r in lines if "_pool" not in r]
    previous = _previous_titles(year)
    unique, seen = [], set()
    for r in rows:
        k = _key(r["title"])
        if k and k not in seen and k not in previous:
            seen.add(k)
            unique.append(r)
    deals = [r for r in unique if r["kind"] == "deal"]
    by_record = defaultdict(list)
    for r in deals:
        by_record[r["record"]].append(r)
    if len(by_record) < MIN_POOL_RECORDS:
        raise SystemExit(f"Only {len(by_record)} deal records in the {year} pool; at least {MIN_POOL_RECORDS} are needed.")

    used: set[str] = set()
    picks: list[tuple[str, dict]] = []

    def take(stratum: str, candidates: list[dict], n: int) -> None:
        candidates = [r for r in candidates if _key(r["title"]) not in used]
        for r in rng.sample(candidates, min(n, len(candidates))):
            used.add(_key(r["title"]))
            picks.append((stratum, r))

    # One headline per record for the random stratum, so syndicated copies do not crowd it out.
    take("random", [rng.choice(v) for _, v in sorted(by_record.items())], N_RANDOM)
    take("hard:cross_border", [r for r in deals if r["countries"] >= 2], N_PER_HARD)
    take("hard:french", [r for r in deals if _FRENCH.search(r["title"])], N_PER_HARD)
    take("hard:large_amount", [r for r in deals if (r.get("usd") or 0) >= 1e9], N_PER_HARD)
    clustered = {r["merged_into"] for r in deals if r.get("merged_into")}
    cluster_rows = [r for r in deals if r.get("merged_into") or r["record"] in clustered]
    if not clustered:                                 # API pools: merged reports sit inside one record
        cluster_rows = [r for r in deals if len(by_record[r["record"]]) >= 2]
    take("hard:duplicate_cluster", cluster_rows, N_PER_HARD)
    take("negative_candidate", [r for r in unique if r["kind"] == "event"], N_NEGATIVE)
    rng.shuffle(picks)
    items = [_item(f"r{k:03d}", r) for k, (_, r) in enumerate(picks)]
    strata = [{"item_id": f"r{k:03d}", "stratum": s} for k, (s, _) in enumerate(picks)]

    # Pairs: reports the system merged, look-alikes it kept apart, and same-company hard negatives.
    groups = defaultdict(list)
    for rid, v in by_record.items():
        head = v[0]
        groups[head.get("merged_into") or rid].append(head)
    merged = [(a, b) for g in groups.values() if len(g) >= 2 for a, b in [tuple(rng.sample(g, 2))]]
    if not clustered:                                 # API pools: two reports folded into one record
        merged = [tuple(rng.sample(v, 2)) for _, v in sorted(by_record.items()) if len(v) >= 2]
    heads = sorted((v[0] for k, v in by_record.items() if not v[0].get("merged_into") and not v[0].get("excluded")),
                   key=lambda r: r.get("date") or "")
    lookalike, hard_negative = [], []
    for i, a in enumerate(heads):
        for b in heads[i + 1:i + 150]:
            if not (a.get("date") and b.get("date")) or abs((date.fromisoformat(b["date"][:10]) - date.fromisoformat(a["date"][:10])).days) > 60:
                continue
            if not (_words(a.get("target")) & _words(b.get("target"))):
                continue
            ua, ub = a.get("usd"), b.get("usd")
            if ua and ub and abs(ua - ub) > 0.05 * max(ua, ub) and dl.normalise_name(a.get("target")) == dl.normalise_name(b.get("target")):
                hard_negative.append((a, b))
            else:
                lookalike.append((a, b))
    pair_picks = [("merged", p) for p in rng.sample(merged, min(N_PAIR_MERGED, len(merged)))] + \
                 [("kept_apart", p) for p in rng.sample(lookalike, min(N_PAIR_LOOKALIKE, len(lookalike)))] + \
                 [("hard_negative", p) for p in rng.sample(hard_negative, min(N_PAIR_HARD_NEGATIVE, len(hard_negative)))]
    rng.shuffle(pair_picks)
    pairs = [{"item_id": f"p{k:03d}", "a": _item("a", a), "b": _item("b", b)} for k, (_, (a, b)) in enumerate(pair_picks)]
    pair_system = [{"item_id": f"p{k:03d}", "system": s} for k, (s, _) in enumerate(pair_picks)]

    out_dir.mkdir(parents=True, exist_ok=True)

    def write(name: str, rows_: list[dict]) -> None:
        (out_dir / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows_))

    write("items.jsonl", items)
    write("pairs.jsonl", pairs)
    write("_strata.jsonl", strata)
    write("_pair_system.jsonl", pair_system)
    for who in ("a", "b"):
        write(f"labels_{who}.jsonl", [{"item_id": i["item_id"], "annotator": "", **LABEL_FIELDS} for i in items])
        write(f"pair_labels_{who}.jsonl", [{"item_id": p["item_id"], "annotator": "", **PAIR_FIELDS} for p in pairs])
    counts, pair_counts = defaultdict(int), defaultdict(int)
    for s in strata:
        counts[s["stratum"]] += 1
    for s in pair_system:
        pair_counts[s["system"]] += 1
    manifest = {"name": f"{year} independent review", "year": year, "seed": seed, "drawn": date.today().isoformat(),
                "pool_snapshot": lines[0].get("snapshot"), "items": len(items), "pairs": len(pairs),
                "strata": dict(counts), "pair_strata": dict(pair_counts),
                "note": (f"The pool holds {len(hard_negative)} same-company, different-amount pairs, so the hard-negative "
                         f"stratum has {pair_counts['hard_negative']} of the {N_PAIR_HARD_NEGATIVE} planned."
                         if pair_counts["hard_negative"] < N_PAIR_HARD_NEGATIVE else ""),
                # The hosted runtime drops Markdown files, so the guide also travels inside the manifest.
                "guidelines_md": (HERE / "GUIDELINES.md").read_text()}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main(args: list[str]) -> None:
    def opt(name: str) -> str | None:
        return args[args.index(name) + 1] if name in args else None

    year = int(opt("--year") or date.today().year)
    out_dir = Path(opt("--out")) if opt("--out") else HERE / str(year)
    if (HERE / str(year) / "manifest.json").exists() and not opt("--out"):
        print(f"The {year} review is already drawn; it is never redrawn, so labels in progress are safe.")
        return
    pool = Path(opt("--pool")) if opt("--pool") else out_dir / "pool.jsonl"
    if opt("--from-api"):
        pool_from_api(opt("--from-api"), year, pool)
    elif opt("--from-export"):
        pool_from_export(Path(opt("--from-export")), pool)
    manifest = build(year, pool, out_dir)
    print(json.dumps({k: v for k, v in manifest.items() if k != "guidelines_md"}, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
