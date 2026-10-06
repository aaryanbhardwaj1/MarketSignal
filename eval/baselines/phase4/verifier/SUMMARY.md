# Phase 4 verifier precision (workstream A): before/after

Dataset: `eval/datasets/verifier-v1` (fresh synthetic; 32 families split by family with seed
20261006: dev 19 families / 42 cases / 144 units, holdout 13 families / 35 cases / 115 units;
holdout SHA-256 `6bb236daef806d6e97499a1b806cab6be6b7199b0e177862d2ae3e68417fb48b`). No
live-v0 items were used. Harness: `python -m marketsignal.evaluation.verifier_eval`.

* **before** = the Phase 3 verifier, run from an untouched snapshot of `backend/src` taken
  before any edit (the harness passes only the keyword arguments a verifier accepts).
* **first-after** = the first Phase 4 verifier. **final-after** = after the review-driven safety
  fixes below (the files `*-after.json` hold final-after).
* Holdout use: run **twice in total**. First at the end of development (before + first-after).
  Second (and final) after the adversarial review, only to measure the safety fixes R1-R6; no
  rule was tuned to holdout scores, and nothing changed after the second run.

| metric | dev before | dev first-after | dev final-after | holdout before | holdout first-after | holdout final-after |
|---|---|---|---|---|---|---|
| false_positive_rejection_rate | 0.101 | 0.0404 | 0.0404 | 0.1304 | 0.058 | 0.058 |
| supported_retention | 0.899 | 0.9596 | 0.9596 | 0.8696 | 0.942 | 0.942 |
| false_negative_acceptance_rate | 0.3556 | 0.2667 | 0.2444 | 0.3043 | 0.3043 | 0.3043 |
| miscited_repaired | 0 | 3 | 0 | 0 | 2 | 0 |
| repair_frequency | 0.6429 | 0.619 | 0.619 | 0.7714 | 0.6571 | 0.6571 |
| regeneration_request_frequency | 0.1429 | 0.1905 | 0.1905 | 0.1429 | 0.1143 | 0.1429 |
| fallback_frequency | 0.1429 | 0.1667 | 0.1667 | 0.1429 | 0.1143 | 0.1429 |
| structural_agreement | 0.8571 | 0.9524 | 0.9524 | 0.8857 | 0.8571 | 0.8857 |
| latency_ms_p50 | 0.3175 | 0.558 | 0.5429 | 0.2912 | 0.5669 | 0.5051 |
| latency_ms_p95 | 0.5095 | 0.8197 | 1.0629 | 0.3875 | 0.7417 | 0.6692 |

Units: dev 99 supported / 45 unsupported+miscited; holdout 69 / 46. Latency is the per-case
median of 5 calls (ms, one process).

## Reading the numbers

* False-positive rejections are still less than half of Phase 3 on both splits (dev 10.1% ->
  4.0%, holdout 13.0% -> 5.8%); the safety fixes cost no FP on either split.
* False-negative acceptance is at or below Phase 3 on both splits (dev 35.6% -> 24.4%, holdout
  30.4% -> 30.4%). No holdout unit moved from removed to accepted in either after-run.
* Re-pointing now needs the target item to name the claim's subject; it fired 0 times on dev
  and holdout (first-after: 3 and 2). Those miscited claims are dropped as in Phase 3.
* Remaining false negatives are mostly outside a deterministic numeric verifier: invented
  entity names and causal claims with no figures, a figure present in the cited item but for
  another period, spelled-out fractions.
* Conflict signal (A7, advisory only): dev 3 TP / 0 FP / 2 FN; holdout 2 TP / 4 FP / 0 FN.
  The false triggers are why a "Conflicting evidence" section is encouraged, not required.
* Gold disagreements left unchanged: F14-b (invented competitor name, not checkable) and
  F26-c (only Gaps unit is unsupported, gold still expects no gaps_missing).

## Review-driven safety fixes

An adversarial review found false-negative regressions against Phase 3. Every probe (55, in
`tests/unit/test_verifier_precision.py::test_review_probe_never_accepts_more_than_phase3`)
asserts that each unit kept without an `[inference]` tag was also kept verbatim by Phase 3.

| Fix | Change | Metric delta (first-after -> final-after) |
|---|---|---|
| R1 alias reassembly / crash | `_canonical` renders only the unit's checked aliases and strips any other `[E#]`; `_PAREN_RE` never matches after a letter, digit or `[`; `_repair_clauses` refuses repairs that create alias-like markers; `runs/synthesis._verify_safely` turns any verifier exception into a failed verification (`verifier_error`, type-only log) | none on the datasets (no such inputs) |
| R2 date masking | no digits are masked any more; only the year of a full date (ISO, d/m/yyyy, "March 3, 2026") is marked temporal; day/month stay checkable figures | none |
| R3 years | cited units: years must be in the cited item's text or visible metadata (`_Run.item_years`); the global set (pack + question) applies only to uncited/[inference] units; "by", "from", "vs/versus" and metric nouns removed from the year cues; year range 1900-2099 everywhere | dev FN 26.7% -> 24.4% (F28-b now rejected) |
| R4 re-pointing | temporal evidence ignored; plain percents not distinctive; the target must contain every content word before the claim's first figure (`_subject_words`) | miscited repaired dev 3 -> 0, holdout 2 -> 0 (now dropped) |
| R5 metadata | a metadata phrase is blanked where it appears (`_mask_phrases`) and covers only its own number; other figures need the item text | none |
| R6 gap statements | an Answer gap must start with the insufficiency phrase (at most 3 words before), be a single clause (no `;`, `, and/but/or`, "and the/no") and state no figures; otherwise the usual [inference]/drop path | none |
| (extra) | `_repair_clauses` refuses units with negation, condition or correction words (not, only, if, unless, false, true, ...) | none |

Holdout regeneration/fallback frequency went 11.4% -> 14.3% (back to Phase 3 level) because
the cases that re-pointing used to rescue now fail and regenerate.

## Rules (final)

* A1: `contract.NumberMention.temporal` = bare 4-digit year 1900-2099 in a date, period, edition
  or title context, full-date years, year ranges. FY/CY labels checked the same way. "2,025
  units"/"2025 respondents"/"rose by 2000"/"2019 sales" stay quantities.
* A2: only `prompts.visible_metadata(item)`; a metadata figure is accepted only inside its exact
  phrase ("Slide 7"), never for another number in the unit.
* A3: re-point (strict, see R4) -> remove unsupported parenthetical/later clause/trailing
  appositive when safe (first clause states a supported figure, no polarity words, no new
  alias) -> drop. Back-reference units (This/These/...) after a dropped unit in Answer or
  Interpretation are dropped.
* A4: `settings.verifier_max_citations` stated in the system prompt and the feedback.
* A5: see R6; gap units listed in `sections["answer_unknowns"]` and `report.gap_statements`.
* A6: one `verification_attempts` row per verified attempt (accepted, repaired, regenerate,
  rejected = failed with no time to regenerate, fallback = regenerated attempt failed too).
