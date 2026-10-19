# Research quality benchmark

This benchmark is intended to evaluate research quality rather than merely whether the API returns an answer.

## Protocol

1. Build a held-out set of real analyst questions across African and US companies, transaction verification, market mapping, sector research, investor activity, company financials, and country risk.
2. For every question, have a reviewer record the required facts, known relevant source URLs, acceptable alternative sources, expected uncertainty, and material claims that must not be guessed.
3. Keep benchmark answers and labels out of the retrieval prompt. Version the dataset and record the code commit, data snapshot, model/provider, and run timestamp.
4. Run every case with the same limits and settings. Store retrieved URLs and evidence IDs, answer text, claim-level citations, latency, token/cost estimates where available, and any fallback mode.
5. Have a second reviewer label material claims as supported, contradicted, unsupported, or not assessable. A valid citation number alone is not a support label.
6. Compare runs before and after a change; do not claim improvement unless the held-out metrics improve without unacceptable regressions.

## Required metrics

- **Retrieval precision:** relevant retrieved source IDs / all retrieved source IDs.
- **Retrieval recall:** relevant retrieved source IDs / expected relevant source IDs.
- **Claim support rate:** material claims supported by the cited passage / material claims reviewed.
- **Field accuracy:** correct values for target, parties, amount, currency, announcement date, stage and valuation.
- **Conflict recall:** known source disagreements detected / known disagreements in the set.
- **Unknown handling:** cases correctly marked insufficient evidence / cases intentionally lacking adequate evidence.
- **Source diversity:** independent publishers and primary sources represented, with syndication deduplicated.
- **Operational quality:** latency, failures, deterministic fallback rate, and estimated model/search cost.

## Current deterministic test fixtures

The automated tests exercise query planning, explicit same-currency amount disagreement flags, missing-date limitations, and metric calculations. They are **unit tests, not a measured real-world accuracy benchmark**. Populate the reviewed held-out set before making numeric claims about research quality.
