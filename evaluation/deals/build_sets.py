"""
Build the deal data-quality evaluation sets from stored raw headlines (data/headlines.jsonl)
and the deal store (data/deals.json). Inputs only: no extractor output is written to the item
files, so labels are made blind to what the extractor produced.

    python -m evaluation.deals.build_sets

Writes evaluation/deals/{extraction,dedup,identity}_items.jsonl. Fixed seed: re-running gives
the same sample.
"""
from __future__ import annotations

import json
import random
import re
from itertools import combinations
from pathlib import Path

from src.engines import deals as dl
from src.engines import investors as inv

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEED = 20261014
N_EXTRACTED, N_REJECTED, N_DEDUP_SAME, N_DEDUP_CANDIDATE, N_IDENTITY = 160, 60, 40, 60, 80

# Headlines the extractor rejected are sampled only if they look transactional, so the
# rejected sample measures missed deals rather than obviously irrelevant news.
_DEALISH = re.compile(
    r"\b(acquir\w*|acquisition|merg\w*|buy\w*|stake|invest\w*|raises?|raised|funding|financ\w*|loan|"
    r"facility|bond|ipo|listing|fund\w*|rach[eè]t\w*|l[eè]ve\w*|lev[ée]e|prise\s+de\s+participation|"
    r"cession|financement|pr[eê]t|aquisi\w*|investimento|financiamento|compra\w*)\b", re.IGNORECASE)


_GENERIC = {"capital", "africa", "african", "bank", "group", "holdings", "holding", "investment", "investments",
            "fund", "funds", "partners", "limited", "international", "global", "finance", "financial", "ventures",
            "company", "corporation", "energy", "power", "solar", "east", "west", "south", "north", "nigeria",
            "kenya", "egypt", "ghana", "morocco", "plc", "development", "world", "management", "asset", "assets",
            "equity", "private", "growth", "services", "technologies", "technology", "digital", "first", "national"}


def _distinct(name: str) -> set[str]:
    return {w for w in dl.normalise_name(name or "").split() if len(w) > 3 and w not in _GENERIC}


def _headlines() -> list[dict]:
    seen, rows = set(), []
    for line in (ROOT / "data" / "headlines.jsonl").open():
        r = json.loads(line)
        key = re.sub(r"\W+", " ", r["title"].lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)
    return rows


def _item(i: str, r: dict) -> dict:
    return {"item_id": i, "title": r["title"], "publisher": r.get("publisher"), "date": r.get("date"),
            "feed": r.get("feed"), "country_hint": r.get("country_hint")}


def extraction_items(rng: random.Random, rows: list[dict]) -> list[dict]:
    extracted, rejected = [], []
    for r in rows:
        d = dl.extract_deal(r["title"], r.get("snippet", ""), published=r.get("date"), publisher=r.get("publisher", ""),
                            url=r.get("url", ""), country_hint=r.get("country_hint"),
                            africa_source=r.get("africa_source", False), rates=lambda c, y: None)
        (extracted if d else rejected).append(r)
    rejected = [r for r in rejected if _DEALISH.search(r["title"])]
    picks = rng.sample(extracted, N_EXTRACTED) + rng.sample(rejected, N_REJECTED)
    rng.shuffle(picks)
    return [_item(f"x{k:03d}", r) for k, r in enumerate(picks)]


def dedup_items(rng: random.Random, rows: list[dict]) -> list[dict]:
    by_url = {r["url"]: r for r in rows}
    store = list(dl.load_deals().values())
    # (a) Pairs of sources the deduplicator merged into one record.
    merged = []
    for d in store:
        srcs = [by_url[s["url"]] for s in d.get("sources") or [] if s.get("url") in by_url]
        merged.extend(combinations(srcs[:4], 2))
    # (b) Pairs of separate records that might be one deal: shared target words or the same amount, within 60 days.
    def words(d: dict) -> set[str]:
        return _distinct(d.get("target"))
    candidates = []
    dated = sorted((d for d in store if d.get("announced")), key=lambda d: d["announced"])
    for i, a in enumerate(dated):
        for b in dated[i + 1:i + 120]:
            if b["announced"][:7] > a["announced"][:7] and (int(b["announced"][5:7]) - int(a["announced"][5:7])) % 12 > 2:
                break
            same_amount = (a.get("amount_usd") and b.get("amount_usd") and a.get("country") == b.get("country")
                           and abs(a["amount_usd"] - b["amount_usd"]) <= 0.02 * a["amount_usd"])
            if (words(a) & words(b)) or same_amount:
                ha = next((by_url[s["url"]] for s in a.get("sources") or [] if s.get("url") in by_url), None)
                hb = next((by_url[s["url"]] for s in b.get("sources") or [] if s.get("url") in by_url), None)
                if ha and hb:
                    candidates.append((ha, hb))
    picks = [("merged", p) for p in rng.sample(merged, min(N_DEDUP_SAME, len(merged)))] + \
            [("separate", p) for p in rng.sample(candidates, min(N_DEDUP_CANDIDATE, len(candidates)))]
    rng.shuffle(picks)
    out = []
    for k, (system, (a, b)) in enumerate(picks):
        out.append({"item_id": f"d{k:03d}", "a": _item("a", a), "b": _item("b", b), "_system": system})
    return out


def identity_items(rng: random.Random) -> list[dict]:
    names = set()
    for d in dl.load_deals().values():
        for n in [d.get("buyer"), d.get("seller")] + list(d.get("investors") or []):
            if n and len(n) > 2:
                names.add(n.strip())
    names = sorted(names)
    resolved = [n for n in names if inv.registry_entry(n)]
    # Pairs the resolver joins (same registry entity, different strings) and look-alike pairs it keeps apart.
    joined = [(a, b) for a, b in combinations(resolved, 2)
              if inv.canonical(a) == inv.canonical(b) and dl.normalise_name(a) != dl.normalise_name(b)]
    apart = [(a, b) for a, b in combinations(names, 2)
             if _distinct(a) & _distinct(b) and inv.canonical(a) != inv.canonical(b)]
    picks = rng.sample(joined, min(N_IDENTITY // 2, len(joined))) + rng.sample(apart, min(N_IDENTITY // 2, len(apart)))
    rng.shuffle(picks)
    return [{"item_id": f"i{k:03d}", "a": a, "b": b} for k, (a, b) in enumerate(picks)]


def main() -> None:
    rng = random.Random(SEED)
    rows = _headlines()
    sets = {"extraction": extraction_items(rng, rows), "dedup": dedup_items(rng, rows), "identity": identity_items(rng)}
    for name, items in sets.items():
        path = HERE / f"{name}_items.jsonl"
        path.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items))
        print(f"{name}: {len(items)} items -> {path.relative_to(ROOT)}")




# ── Held-out sets (built after the development-set fixes, never used to tune) ──

HELDOUT_SEED = 20261015
N_HO_EXTRACTED, N_HO_REJECTED, N_HO_NAMES = 120, 40, 120


def heldout() -> None:
    rng = random.Random(HELDOUT_SEED)
    rows = _headlines()
    dev = {json.loads(l)["title"] for l in (HERE / "extraction_items.jsonl").open()}
    rows = [r for r in rows if r["title"] not in dev]
    extracted, rejected = [], []
    for r in rows:
        d = dl.extract_deal(r["title"], r.get("snippet", ""), published=r.get("date"), publisher=r.get("publisher", ""),
                            url=r.get("url", ""), country_hint=r.get("country_hint"),
                            africa_source=r.get("africa_source", False), rates=lambda c, y: None)
        (extracted if d else rejected).append(r)
    rejected = [r for r in rejected if _DEALISH.search(r["title"])]
    picks = rng.sample(extracted, N_HO_EXTRACTED) + rng.sample(rejected, N_HO_REJECTED)
    rng.shuffle(picks)
    (HERE / "heldout_extraction_items.jsonl").write_text(
        "".join(json.dumps(_item(f"h{k:03d}", r), ensure_ascii=False) + "\n" for k, r in enumerate(picks)))
    # Party names, one at a time: half that the registry resolves, half that it does not.
    dev_names = set()
    for l in (HERE / "identity_items.jsonl").open():
        it = json.loads(l)
        dev_names |= {it["a"], it["b"]}
    names = set()
    for d in dl.load_deals().values():
        for n in [d.get("buyer"), d.get("seller")] + list(d.get("investors") or []):
            if n and len(n.strip()) > 2 and n.strip() not in dev_names:
                names.add(n.strip())
    names = sorted(names)
    known = [n for n in names if inv.registry_entry(n)]
    other = [n for n in names if not inv.registry_entry(n)]
    picks = rng.sample(known, min(N_HO_NAMES // 2, len(known))) + rng.sample(other, N_HO_NAMES // 2)
    rng.shuffle(picks)
    (HERE / "heldout_names_items.jsonl").write_text(
        "".join(json.dumps({"item_id": f"n{k:03d}", "name": n}, ensure_ascii=False) + "\n" for k, n in enumerate(picks)))
    print(f"held-out: {N_HO_EXTRACTED + N_HO_REJECTED} headlines, {len(picks)} names")


if __name__ == "__main__":
    import sys
    heldout() if "--heldout" in sys.argv else main()
