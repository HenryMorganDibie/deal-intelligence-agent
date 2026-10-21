# Independent review: labelling guide

Each year a fresh sample is drawn into `evaluation/review/<year>/`. Two annotators label every item independently; a third person resolves disagreements. Published
data-quality scores change only after both label files and the adjudication are complete.

## Who may label

- People who read African deal news, such as fund associates, deal-database researchers, business
  journalists or finance postgraduates. At least one annotator should read French.
- Not the people who built or tuned the pipeline. Annotators must not discuss items with each other
  before adjudication.

## What you receive

| File | Contents |
|---|---|
| `items.jsonl` | About 200 headlines (the exact count is in `manifest.json`): `item_id`, `title`, `publisher`, `date`. Nothing the system extracted. |
| `pairs.jsonl` | About 100 pairs of headlines: are they the same transaction? |
| `labels_a.jsonl` / `labels_b.jsonl` | Blank label rows for annotator A or B, one per item. |
| `pair_labels_a.jsonl` / `pair_labels_b.jsonl` | Blank pair rows for A or B. |

Do not open `_strata.jsonl`, `_pair_system.jsonl` or `pool.jsonl`: they reveal how items were chosen
and what the system decided. Write your name or initials in `annotator` on every row you fill.

Label from the headline, publisher and date. You may open the article to confirm a fact; record what
you checked in `note`. Mark anything you are unsure of `"confidence": "low"` rather than guessing.

## Headline fields

| Field | Values | Rule |
|---|---|---|
| `is_transaction` | `true` / `false` | A specific completed, agreed or announced private-market transaction: an equity round, acquisition, merger, exit, loan or facility to a named borrower, fund close, IPO. Not: market sizes, sovereign or multilateral bond issues, grants, CSR programmes, plans with no counterparty, legal disputes, commentary, leadership changes. |
| `in_scope` | `true` / `false` | `true` when at least one party (target, buyer, seller, investor, borrower or fund manager) is African or the asset is in Africa. |
| `scope_reason` | free text | Required when `in_scope` is `false` or `is_transaction` is `false`, e.g. "no African party", "sovereign bond". |
| `deal_type` | `equity_funding`, `debt_financing`, `acquisition`, `merger`, `exit`, `fund_raise`, `ipo`, `joint_venture` | `null` when not a transaction. A minority stake bought by an investor is `equity_funding`; control (50% or more) is `acquisition`. A loan, credit line, facility or bond to a company is `debt_financing`. |
| `stage` | `rumoured`, `announced`, `completed` | "agrees to", "to acquire", "plans", "set to", "in talks" are `announced` (talks and reports are `rumoured`). Only closing, completion or a final close is `completed`. |
| `target` | company name | The company raising, being acquired or borrowing; for a fund raise, the fund or its manager. Name only: "Tonaton", not "Ghanaian-based classifieds outlet Tonaton". |
| `acquirer_or_lead` | name or `null` | Buyer, lead investor or lender. |
| `other_parties` | list | Co-investors, sellers. |
| `amount`, `currency` | number, ISO code | The transaction amount as stated (e.g. `85000000`, `"ZAR"`). `null` when none is given. |
| `amount_kind` | `deal_size`, `valuation`, `market_size`, `programme_or_pledge`, `none` | What the headline's figure is. "at a $3.2bn valuation" is `valuation`; "Africa's $1.7 trillion trade market" is `market_size`; "$200bn for Nigeria and others" from a multilateral is `programme_or_pledge`. Only `deal_size` belongs in `amount`. |
| `stake_pct` | number or `null` | Percentage acquired, if stated. |
| `country` | ISO 3166 alpha-2 or `null` | The target's home market. For an asset deal (a hotel, a field, a plant), where the asset is. For a fund, the manager's home market. |
| `country_basis` | `named_in_headline`, `known_entity`, `unclear` | `named_in_headline` when the headline names the country, a demonym, a city or "SA's"; `known_entity` when you know the company's home; `unclear` otherwise (and leave `country` `null`). |
| `africa_wide` | `true` / `false` | `true` for pan-African funds and programmes with no single home market; then `country` is `null`. |
| `asset_location` | ISO code or `null` | Only for asset deals whose asset sits outside the buyer's country. |
| `language` | `en`, `fr`, `pt`, `ar`, ... | Headline language. |
| `confidence` | `high` / `low` | `low` whenever you had to guess any field. |

## Pair fields

| Field | Values | Rule |
|---|---|---|
| `same_transaction` | `true` / `false` | `true` when both headlines report the same transaction, even if worded, dated or valued differently. A first close and a later final close of one fund are different transactions. Two raises by one company months apart are different. |
| `confidence` | `high` / `low` | |

## Worked examples

| Headline | Key labels |
|---|---|
| Kenya's Jiji acquires Ghanaian-based classifieds outlet Tonaton | transaction; `acquisition`; target `Tonaton`; acquirer `Jiji`; country `GH` (`named_in_headline`) |
| Flutterwave raises Series E funding at $3.2bn valuation; Ripple participates | transaction; `equity_funding`; amount `null`; `amount_kind` `valuation` |
| Native Acquires Frontline Research Group ... for Africa's $1.7 Trillion Traditional Trade Market | transaction; `acquisition`; amount `null`; `amount_kind` `market_size` |
| La RCI lève 52,9 milliards FCFA sur le marché des titres publics | not a transaction (`sovereign treasury issue`); `language` `fr` |
| Zimbabwe's Rainbow Tourism Group invests R100 million in Cape Town hotel acquisition | transaction; `acquisition`; country `ZA`; `asset_location` `ZA` |
| Ventures Platform reaches $84m final close for second fund | transaction; `fund_raise`; `completed`; country `NG` (`known_entity`) |
| Bain Capital to acquire UK vitamins maker Vitabiotics in $1.2 billion deal | transaction; `in_scope` `false` (`no African party`) |

## Adjudication

The adjudicator reads only the rows where A and B differ, writes the final label to
`adjudicated_labels.jsonl` / `adjudicated_pair_labels.jsonl` with both annotator names and a reason,
and never edits A's or B's files. Then run the scorer and publish the results with their sample sizes
and 95% intervals next to the existing figures.
