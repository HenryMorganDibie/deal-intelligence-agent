# Evaluation sets

Labelled samples that measure the parts of the system a buyer has to trust: whether a deal record is
right, whether two records are one deal, whether two names are one investor, and whether a news
item's event belongs to the company it names. Signal outcomes (did the event happen, did the price
move) are measured separately by the walk-forward backtest: `docs/evaluation_report.json` and
`docs/backtest_predictions.csv`, rebuilt with `python main.py backtest --evaluation`.

Every number carries its sample size and a 95% Wilson interval. The hosted API serves the results at
`/api/evaluation` and every file below at `/api/evaluation/files/{name}`; the web app's evaluation
page renders them.

## When the numbers change

The signal backtest re-runs every quarter (`.github/workflows/backtest.yml`, 2 January, April, July
and October): it replays the latest 18 monthly dates whose 90-day outcome windows have closed, over
the universe in `docs/backtest_universe.csv`, and commits the regenerated report, measured tables and
prediction file, which redeploys the site. Live outcomes from hosted briefs update hourly. The deal
and attribution sets change only when new labelled samples are drawn.

## How the labels were made

- Items were sampled with fixed seeds from stored data (`build_sets.py`). Item files contain inputs
  only, so labels were made blind to what the system produced.
- Labels were written by an AI annotator working from the source text alone, with written rules
  (the prompts are reproduced in each set's notes below) and a reason for every non-obvious call.
  Items the annotator was unsure of are marked `"confidence": "low"` and reported separately.
- **They have not yet been reviewed by an independent human.** Treat them as a documented first pass:
  every item and label is published, and disagreements change the numbers transparently.
- Attribution is tested on **real headlines only**, each with its real publisher, date and link.

## Development and held-out sets

The first deal sets (`extraction_*`, `dedup_*`, `identity_*`) were used as
**development sets**: their errors were read and the system was changed. Their post-fix numbers are
therefore optimistic, and `results_baseline.json` keeps the numbers from before any change.

The **held-out sets** (`heldout_*`) and both attribution sets were drawn and labelled after
those changes and have never been used for tuning. They are the numbers to rely on. Once a held-out
set's errors are used to change the system, it becomes a development set and a new held-out set must
be drawn (`python -m evaluation.deals.build_sets --heldout` with a new seed).

## Results (14 Oct 2026)

Deal extraction, raw headline to record (`python -m evaluation.deals.score`):

| Measure | Development, before | Development, after | Held-out |
|---|---|---|---|
| Genuine transaction (precision) | 82% [76–88] n=160 | 82% [76–88] n=160 | 82% [75–88] n=120 |
| Deal-like headlines caught (recall) | 92% [86–95] n=144 | 92% [86–95] n=144 | 92% [85–96] n=108 |
| Every field right | 46% [37–54] n=132 | 50% [42–58] n=132 | 71% [61–79] n=99 |

Held-out field accuracy: deal type 94% [87–97], stage 93% [86–96], target 94% [87–97], buyer or
lead 87% [75–94] (n=53), amount and currency 95% [86–98] (n=59), stake 92% [65–98] (n=12), country
88% [79–94] (n=69). Results by country, source, language and deal type are in `deals/results.json`.

Stage conventions differ between the sets: the held-out labelling instructions stated the product's
convention that a present-tense acquisition headline ("X acquires Y") is *announced*, not completed;
the development labels often called it completed. Part of the stage gap between the sets is that
convention, not extractor quality.

Recall is measured on a sample enriched for rejected deal-like headlines, so it measures misses
among plausible candidates, not coverage of every deal that happened.

Deduplication (development): merged reports that are one deal 98% [87–100] n=40; separate records
that are actually one deal, among look-alike pairs, 43% [32–56] n=60. Missed duplicates are the main
deduplication weakness.

Identity: name pairs the resolver joins that are one entity rose from 38% [24–53] to 100% [82–100]
(n=18) on the development set once combined names ("IFC and Proparco") are split and headline
fragments ("Tolaram Welcomes IFC") are no longer credited to anyone. Held-out: valid names resolved
to the right organisation 96% [88–98] n=70; malformed names caught 50% [24–76] n=10.

Attribution (`python -m evaluation.attribution.score`), on real headlines about the 46 backtest
companies (`attribution/build_sets.py`):

| Set | Measure | Before the 14 Oct rule changes | After |
|---|---|---|---|
| Random sample, 400 headlines (58 with an event) | Precision | 80% [49–94] (8/10) | 86% [65–95] (18/21) |
| | Recall | 13% [7–24] (8/60) | 30% [20–42] (18/60) |
| | False alarms on no-event headlines | 1% [0–2] (2/342) | 1% [0–3] (3/342) |
| Hard cases, 280 headlines (49 with an event) | Precision | 71% [47–87] (12/17) | 68% [46–85] (13/19) |
| | Recall | 24% [14–37] (12/50) | 26% [16–40] (13/50) |

On real news the engine is rarely wrong when it fires, but it misses most events: recall is the
weakness, worst for short names and tickers it is not given (0 of 10) and for events at
subsidiaries and parents. Both sets were labelled after the rule changes and were not used to make
them. Every error is in `attribution/errors.jsonl` with its source link.

## Files

| File | What it is |
|---|---|
| `deals/build_sets.py` | Samplers (fixed seeds) |
| `deals/extraction_items.jsonl`, `extraction_labels.jsonl` | 220 development headlines and labels |
| `deals/heldout_extraction_items.jsonl`, `heldout_extraction_labels.jsonl` | 160 held-out headlines and labels |
| `deals/dedup_items.jsonl`, `dedup_labels.jsonl` | 100 report pairs; `_system` records what the deduplicator did |
| `deals/identity_items.jsonl`, `identity_labels.jsonl` | 80 name pairs |
| `deals/heldout_names_items.jsonl`, `heldout_names_labels.jsonl` | 80 held-out party names |
| `deals/score.py`, `results.json`, `results_baseline.json`, `errors.jsonl` | Scorer, results, every error |
| `attribution/build_sets.py` | Samplers for the real-headline sets (fixed seed) |
| `attribution/natural_items.jsonl`, `natural_labels.jsonl` | 400 random real headlines and labels |
| `attribution/hard_items.jsonl`, `hard_labels.jsonl` | 280 hard-case real headlines and labels |
| `attribution/score.py`, `results.json`, `results_before_rule_changes.json`, `errors.jsonl` | Scorer, results, every error |
