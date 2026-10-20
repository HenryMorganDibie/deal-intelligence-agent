"""
Draw the 2026 independent-review sample: headlines and report pairs for two human annotators.

    python -m evaluation.review_2026.build --pool evaluation/review_2026/pool.jsonl

The pool is a snapshot of 2026 deal source headlines and deal-like event headlines from the hosted
store (see pool.jsonl's header row for the query date). Item files carry the headline, publisher and
date only, never the system's extraction, so labels stay blind. The stratum of each item and the
system's merge decision for each pair are written to separate files that annotators must not open.
Fixed seed: re-running on the same pool gives the same sample.

    --from-export PATH   rebuild pool.jsonl from a raw store export first
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from src.engines import deals as dl

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEED = 20261020
N_RANDOM, N_PER_HARD, N_NEGATIVE = 120, 15, 20
N_PAIR_MERGED, N_PAIR_LOOKALIKE, N_PAIR_HARD_NEGATIVE = 40, 40, 20

_FRENCH = re.compile(r"(?i)\b(l[eè]ve|rach[eè]te|acquiert|c[eè]de|milliards?|financement|pr[eê]t|lev[ée]e|investit)\b")
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


def _key(title: str) -> str:
    return re.sub(r"\W+", " ", (title or "").lower()).strip()


def _words(name: str) -> set[str]:
    return {w for w in dl.normalise_name(name or "").split() if len(w) > 3 and w not in _GENERIC}


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
    header = {"_pool": "2026 review", "snapshot": date.today().isoformat(), "rows": len(rows)}
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in [header, *rows]))
    print(f"pool: {len(rows)} headlines -> {out.relative_to(ROOT)}")


def _previous_titles() -> set[str]:
    seen = set()
    for path in [*(ROOT / "evaluation" / "deals").glob("*_items.jsonl"), *(ROOT / "evaluation" / "attribution").glob("*_items.jsonl")]:
        for line in path.open():
            item = json.loads(line)
            for t in (item.get("title"), (item.get("a") or {}).get("title") if isinstance(item.get("a"), dict) else None,
                      (item.get("b") or {}).get("title") if isinstance(item.get("b"), dict) else None):
                if t:
                    seen.add(_key(t))
    return seen


def _item(item_id: str, r: dict) -> dict:
    return {"item_id": item_id, "title": r["title"], "publisher": r.get("publisher"), "date": r.get("date")}


def build(pool_path: Path) -> None:
    rng = random.Random(SEED)
    lines = [json.loads(l) for l in pool_path.open()]
    rows = [r for r in lines if "_pool" not in r]
    previous = _previous_titles()
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
    take("hard:duplicate_cluster", [r for r in deals if r.get("merged_into") or r["record"] in clustered], N_PER_HARD)
    take("negative_candidate", [r for r in unique if r["kind"] == "event"], N_NEGATIVE)
    rng.shuffle(picks)
    items = [_item(f"r{k:03d}", r) for k, (_, r) in enumerate(picks)]
    strata = [{"item_id": f"r{k:03d}", "stratum": s} for k, (s, _) in enumerate(picks)]

    # Pairs: reports the system merged, look-alikes it kept apart, and same-company hard negatives.
    record_rows = {rid: v for rid, v in by_record.items()}
    groups = defaultdict(list)
    for rid, v in record_rows.items():
        head = v[0]
        groups[head.get("merged_into") or rid].append(head)
    merged = [(a, b) for g in groups.values() if len(g) >= 2 for a, b in [tuple(rng.sample(g, 2))]]
    heads = sorted((v[0] for k, v in record_rows.items() if not v[0].get("merged_into") and not v[0].get("excluded")),
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

    def write(name: str, rows_: list[dict]) -> None:
        (HERE / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows_))

    write("items.jsonl", items)
    write("pairs.jsonl", pairs)
    write("_strata.jsonl", strata)
    write("_pair_system.jsonl", pair_system)
    for who in ("a", "b"):
        write(f"labels_{who}.jsonl", [{"item_id": i["item_id"], "annotator": "", **LABEL_FIELDS} for i in items])
        write(f"pair_labels_{who}.jsonl", [{"item_id": p["item_id"], "annotator": "", **PAIR_FIELDS} for p in pairs])
    counts = defaultdict(int)
    for s in strata:
        counts[s["stratum"]] += 1
    pair_counts = defaultdict(int)
    for s in pair_system:
        pair_counts[s["system"]] += 1
    manifest = {"name": "2026 independent review", "seed": SEED, "drawn": date.today().isoformat(),
                "pool_snapshot": lines[0].get("snapshot"), "items": len(items), "pairs": len(pairs),
                "strata": dict(counts), "pair_strata": dict(pair_counts),
                "note": (f"The pool holds {len(hard_negative)} same-company, different-amount pairs, so the hard-negative "
                         f"stratum has {pair_counts['hard_negative']} of the {N_PAIR_HARD_NEGATIVE} planned."
                         if pair_counts["hard_negative"] < N_PAIR_HARD_NEGATIVE else "")}
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    args = sys.argv[1:]
    pool = HERE / "pool.jsonl"
    if "--from-export" in args:
        pool_from_export(Path(args[args.index("--from-export") + 1]), pool)
    if "--pool" in args:
        pool = Path(args[args.index("--pool") + 1])
    build(pool)
