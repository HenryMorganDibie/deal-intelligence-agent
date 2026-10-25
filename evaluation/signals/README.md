# Independent signal-taxonomy evaluation

This is a blinded pilot evaluation for the eight existing canonical signal types. It compares the deterministic production pattern rules on the same items before and after PR #21.

## Sample and limits

- 168 items, drawn from the pre-existing `holdout` split of `docs/automation/event_label_queue.jsonl` as it existed at commit 73298b195faa.
- Reviewers receive only headline, publisher, date, snippet and source URL. They must not inspect model predictions or each other's labels.
- This is a pilot from the product's monitored business-news feed, not a probability sample of every corporate announcement in Africa and the US. Report results as feed-specific and preliminary. It is not large enough to make confident claims for rare event types.
- The items are currently unlabelled. Precision/recall results must not be published until two independent reviewers finish, disagreements are adjudicated, and the scorer completes.
- Because the rules in PR #21 were already tuned using earlier examples, do not use this pilot to tune rules and then continue calling it held-out. If results drive changes, draw a fresh holdout.

## Annotation procedure

Two reviewers independently label every item. Ideally reviewers understand corporate finance and regulatory announcements; at least one should be comfortable with French-language reporting. Do not label together. An adjudicator resolves disagreements into `adjudicated_labels.jsonl`.

For each headline and snippet, list every canonical signal type that is genuinely evidenced by the source. This is multi-label: one article may contain more than one signal. Use an empty array when none of the eight types is supported. Do not infer a signal from sector context, rumours without evidence, or an event that is merely discussed as hypothetical. Prefer the source article if the headline is ambiguous; quote evidence in `note`. Use `confidence=low` rather than guessing. The signal type must represent the event, not whether the event is financially good or bad.

Canonical labels (use exact strings):
- `m_and_a_activity`: concrete M&A, sale/divestiture, acquisition process, exit or IPO preparation/process.
- `credit_risk`: evidence of worsening ability to meet obligations, liquidity/cash-runway stress, missed payments, default or covenant breach. Healthy refinancing alone is not credit risk.
- `distressed_asset`: insolvency, administration, receivership, liquidation, business rescue or distressed sale.
- `earnings_surprise`: earnings/result materially beats or misses expectations, profit warning, or withdrawal/revision of guidance.
- `leadership_change`: executive/founder/C-suite departure, appointment or material board change.
- `regulatory_action`: material regulator/exchange enforcement, investigation, licence action, listing/prospectus decision, or a regulator blocking a transaction.
- `debt_restructuring`: distressed restructuring, covenant waiver, amend-and-extend, debt exchange or material refinancing. Routine new debt issuance alone is not a restructuring signal.
- `insider_activity`: material director/executive/insider or beneficial-owner transactions and ownership/stake changes. Ordinary fundraising is not insider activity.

`event_subtypes` is optional and should map a canonical label to a short human-readable subtype when clear. `market` is one of `africa`, `us`, `other`, or `unclear`; use `unclear` unless the source clearly establishes the event's market. `confidence` is `high`, `medium`, or `low`.

## Scoring

From the repository root, ensure the baseline commit is available and run:

```bash
git fetch --no-tags origin 8e02ff18bc10b486942050538d2431db8f2f0dd2
python -m evaluation.signals.score
```

The scorer refuses incomplete adjudicated labels. It reports precision, recall, F1, 95% Wilson intervals, sample counts, false positives/misses, per-market breakdowns where sample sizes permit, and the paired change from baseline to PR #21. Pattern-level results measure deterministic rule coverage; they are not a substitute for the walk-forward event-outcome backtest or end-to-end production evaluation.
