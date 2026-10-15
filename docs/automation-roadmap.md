# Daily learning pipeline

`.github/workflows/daily-learning-pipeline.yml` runs every day at 03:00 UTC. It runs
[`scripts/daily_pipeline.py`](../scripts/daily_pipeline.py), then opens or updates a
pull request with new review queues, collected data, and promoted models. It never
pushes generated results directly to `main`; merging the pull request publishes
the updated site through the repository's normal deployment integration. The
workflow can also be started manually from GitHub Actions.
Each run has a 15-minute hard timeout (at most about 450 runner-minutes in a
30-day month). Together with the existing four-shard monthly backtest and its
weekly cache keepalive, the configured caps remain below the 2,000-minute
monthly allowance documented in `backtest.yml`.

## What the workflow does

1. **Event classifier:** Collects current African business headlines and adds
   unseen items to `docs/automation/event_label_queue.jsonl`. Every item has an
   empty `label` until a reviewer labels it. The 680-item natural/hard attribution
   evaluation set remains read-only and is used only as a held-out evaluation set.
   Training is gated until 1,000 reviewed examples are available. A bag-of-words
   classifier is evaluated against the existing deterministic rules and is saved
   only if locked-set macro-F1 improves by at least 0.02.
2. **Entity resolution:** Extracts likely duplicate deal-party names and queues
   fuzzy pairs in `docs/automation/entity_match_queue.jsonl`. Labels are split by
   stable pair ID into train and holdout. A learned matcher is gated on minimum
   sample sizes, at least 98% holdout precision, and an F1 improvement over exact
   name normalization. It only creates suggestions; it never merges companies
   automatically.
3. **Financial anomalies:** Fetches annual financials for four previously
   uncollected tickers per day from the backtest universe and stores sourced
   observations in `docs/automation/financial_observations.jsonl`. Simple
   screening flags are not anomaly labels; they remain reviewable and are not
   presented as confirmed findings.
4. **Graph intelligence:** Extracts buyer/target relationships from collected
   deal headlines and accumulates them in
   `docs/automation/relationship_graph.json`. Each edge retains its source title,
   publisher and URL.
5. **Learned ranking:** Trains a logistic ranker from the labelled,
   confirmable rows in `docs/backtest_predictions.csv`, using an 80/20
   chronological split. The candidate is written to
   `docs/automation/learned_ranker.json` only if it beats alpha by at least two
   percentage points at precision@top-20% and beats the prevalence baseline on
   Brier score. A failed candidate leaves the previous model untouched.

The daily status and holdout results are published in
[`learning_pipeline.json`](./automation/learning_pipeline.json) and
[`web/data/investment_ideas.json`](../web/data/investment_ideas.json). Per-model
reports and the queues are kept alongside them in `docs/automation/`.

## Reviewing labels

Review queues are append-only JSON Lines files. To label an event item, set its
`label` to an object such as:

```json
{"about_target":true,"expected":["regulatory_action"],"confidence":"high"}
```

`expected` may contain zero or more signal type names from the signal registry.
Use `about_target: false` and an empty `expected` list when the headline is not
about the target company. For entity pairs, set `same_entity` to `true` or `false`
and fill `canonical_entity` when the pair refers to the same organization. Keep
the generated `review_split` unchanged.

Training is not inferred from the deterministic rules. Until a candidate clears
its separate holdout gate, the running production detector remains unchanged.
No investment instrument is labelled a personalized buy recommendation: the
investing page is educational and explains risks, fees, suitability and drawbacks.
