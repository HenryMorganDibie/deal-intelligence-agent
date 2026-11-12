"""Flatten the per-state polling-unit files into one CSV: code, state/lga/ward codes and names, unit, kind."""
import csv, glob, gzip, json, re, sys
root, out = sys.argv[1], sys.argv[2]
rows, seen = [], set()
def clean(s):
    return re.sub(r"\s+", " ", (s or "").strip())
for f in sorted(glob.glob(root + "/*.json")):
    if f.endswith("summary.json"):
        continue
    st = json.load(open(f))["state"]
    for l in st["lgas"]:
        for w in l["wards"]:
            for p in w.get("pollingUnits") or []:
                name, remark = clean(p.get("name")), clean(p.get("remark")).upper()
                code = clean(p.get("delimitation"))
                if not name or not remark or not code:
                    continue                      # one blank placeholder per ward in the source
                s, lg, wd, un = (f"{int(x):0{n}d}" for x, n in zip(code.split("/"), (2, 2, 2, 3)))
                code = f"{s}/{lg}/{wd}/{un}"             # a few source codes write the ward as 011, not 11
                if code in seen:
                    continue
                seen.add(code)
                rows.append([code, s, clean(st["name"]), lg, clean(l["name"]), wd, clean(w["name"]), un, name,
                             "existing" if remark == "EXISTING PU" else "new"])
# The polling-unit code is INEC's identifier; where a few units sit under a neighbouring ward's name in the source,
# the ward takes the name most of its units carry.
import collections
names = collections.defaultdict(collections.Counter)
for r in rows:
    names[(r[1], r[3], r[5])][r[6]] += 1
fixed = 0
for r in rows:
    best = names[(r[1], r[3], r[5])].most_common(1)[0][0]
    if r[6] != best:
        r[6] = best
        fixed += 1
print("ward names corrected from the unit code:", fixed)
rows.sort(key=lambda r: r[0])
with gzip.open(out, "wt", newline="", compresslevel=9) as fh:
    wr = csv.writer(fh)
    wr.writerow(["code", "state_code", "state", "lga_code", "lga", "ward_code", "ward", "unit_code", "name", "kind"])
    wr.writerows(rows)
print(len(rows), "units;", len({r[1] for r in rows}), "states;", len({r[1]+r[3] for r in rows}), "LGAs;",
      len({r[1]+r[3]+r[5] for r in rows}), "wards")
