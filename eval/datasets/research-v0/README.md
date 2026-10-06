# research-v0

Phase 4 research-mode evaluation set: compares the standard single-pass path with the bounded research agent (plan §19, ADR-0007, ADR-0015). Built by `scripts/build_research_v0.py` (deterministic; `--check` diffs a rebuild against these files, `--verify-db` checks every handle against the seeded database). Do not edit `items.json` by hand.

All data is fictional (synthetic seed corpus). Questions and ids are new; facts come from `seed_data/fact_ledger.json` and every gold fact names its ledger `fact_id`.

## Schema

Compatible with the grounded-eval harness (`id, workspace, category, question, expect, gold_facts[{fact_id, handles, value, unit}], source_classes, canary, provenance, origin_split`). Extra fields: `router_expectation` (`research` | `standard`: what a reasonable router should pick from the question alone), `notes` (why multi-step search should or should not help; for `first_pass_insufficient` why the obvious first query misses part of the gold), `split`, `group`, `gold_source_classes`, `ledger_contradictions`, `leakage`, and per gold fact `anchor_handle`, `source_code`, `source_class`. `source_classes` is always `[]` (no filters). `handles` is any-of per fact; every listed fact is required.

## Gold

- `anchor_handle`: the active parent containing the fact's planted anchor, located with `evaluation.gold.locate` in the seeded DB; equal to retrieval-v0 `satisfied_by` for every fact that retrieval-v0 also uses.
- Alternates: retrieval-v0's dual-judged `also_satisfied_by`, plus restatements reviewed for this set (`ALTERNATES` in the builder, single reviewer, each with a probe string that must still occur in the parent). Candidates were found by value and surface-form search over all active parents; candidates that state only part of a fact or a different period/definition were rejected (e.g. 'a little under 20%' for NS-127, NPS mentions without the Q2 period).
- Per-item override: `R-SC-11` also asks for the rescan fee, which only the Kinetic Lab page states, so its gold is the anchor alone.
- The grounded harness checks each numeric ledger `value` appears in the answer, so every question asks for the ledger value of each of its facts.
- No superseded, injection-carrier or canary-output facts are used.

## Categories and split

| category | dev | test | total |
|---|---|---|---|
| conflict_search | 3 | 2 | 5 |
| customer_competitor | 2 | 3 | 5 |
| customer_internal | 2 | 3 | 5 |
| first_pass_insufficient | 2 | 4 | 6 |
| identifier_then_semantic | 2 | 4 | 6 |
| insufficient_stop | 2 | 4 | 6 |
| multi_class | 3 | 3 | 6 |
| reformulation | 2 | 4 | 6 |
| simple_control | 5 | 7 | 12 |
| **all** | 23 | 34 | 57 |

Router expectation: {'research': 36, 'standard': 21}. Expect: {'answer': 46, 'conflict': 5, 'insufficient': 6}.

Split: 37 leakage groups. Items are union-found when they share a gold fact, a ledger-related fact (contradiction, superseded and distractor pairs) or an anchor parent; whole groups are assigned by a greedy pass (largest first, ties by sha256(`research-v0`:group)) followed by deterministic single-group flips that reduce the squared deviation from 40% dev per category and overall. No fact appears in both splits (validated). Alternate (restatement) parents are not used for grouping - summary documents restate many facts and would collapse the set into one group; 8 alternate parents are shared across splits: `NORTHSTAR/BRAND-STRATEGY@v1:P1.B2`, `NORTHSTAR/BRAND-STRATEGY@v1:P2.B1`, `NORTHSTAR/BRAND-STRATEGY@v1:P5.B2`, `NORTHSTAR/BRAND-STRATEGY@v1:P5.B4`, `NORTHSTAR/PERSO-PILOT@v1:S1.B12`, `NORTHSTAR/PERSO-PILOT@v1:S1.B8`, `NORTHSTAR/Q3-REVIEW@v1:SL3`, `NORTHSTAR/Q3-REVIEW@v1:SL7`.

## Provenance

Hand written for this dataset (`hand_written:research-v0`, `hand_written:ledger-contradiction` for conflict items, `hand_written:topic-not-in-corpus` for insufficient items). Insufficient topics were checked absent by keyword search over every active parent in the workspace (patents, emissions, inventory turnover, distribution centres, debt, licensing/membranes, share price).

## Leakage checks

Each question is compared with all 141 retrieval-v0 (dev and test) and grounded-v0 questions using normalized-token Jaccard: lowercase alphanumeric tokens (ids such as `rv-00412` kept whole), once with all tokens and once without stopwords. The build fails if either exceeds 0.6. Exact-text copies are also rejected, and duplicate questions within the set fail validation. verifier-v1 is built concurrently and is not compared; this set contains no verifier-style (citation perturbation or adversarial) items.

Nearest reference shown with its origin (`dev`/`test` = retrieval-v0 split, `grounded` = grounded-v0).

| item | split | max J (all) | nearest | max J (content) | nearest |
|---|---|---|---|---|---|
| R-MC-01 | dev | 0.167 | G-C3 (grounded) | 0.208 | G-I7 (grounded) |
| R-MC-02 | test | 0.234 | G-A2 (grounded) | 0.194 | G-A2 (grounded) |
| R-MC-03 | dev | 0.288 | R0-050 (dev) | 0.256 | R0-050 (dev) |
| R-MC-04 | test | 0.200 | R0-002 (dev) | 0.194 | R0-002 (dev) |
| R-MC-05 | dev | 0.273 | R0-060 (dev) | 0.261 | R0-060 (dev) |
| R-MC-06 | test | 0.167 | R0-064 (dev) | 0.156 | G-C3 (grounded) |
| R-IT-01 | test | 0.306 | R0-038 (dev) | 0.292 | R0-038 (dev) |
| R-IT-02 | test | 0.269 | R0-021 (test) | 0.333 | R0-021 (test) |
| R-IT-03 | test | 0.194 | R0-001 (dev) | 0.143 | R0-001 (dev) |
| R-IT-04 | test | 0.226 | R0-022 (test) | 0.200 | R0-022 (test) |
| R-IT-05 | dev | 0.206 | R0-033 (test) | 0.107 | R0-057 (test) |
| R-IT-06 | dev | 0.167 | R0-038 (dev) | 0.250 | R0-024 (dev) |
| R-CC-01 | test | 0.200 | G-C1 (grounded) | 0.111 | G-I2 (grounded) |
| R-CC-02 | test | 0.111 | G-E2 (grounded) | 0.050 | R0-021 (test) |
| R-CC-03 | dev | 0.120 | R0-046 (dev) | 0.071 | G-C2 (grounded) |
| R-CC-04 | test | 0.182 | R0-051 (dev) | 0.152 | R0-036 (dev) |
| R-CC-05 | dev | 0.259 | G-C5 (grounded) | 0.278 | G-C5 (grounded) |
| R-CI-01 | test | 0.190 | R0-048 (dev) | 0.200 | R0-048 (dev) |
| R-CI-02 | dev | 0.464 | R0-001 (dev) | 0.421 | R0-001 (dev) |
| R-CI-03 | test | 0.136 | G-C1 (grounded) | 0.045 | G-I1 (grounded) |
| R-CI-04 | test | 0.405 | R0-004 (dev) | 0.391 | R0-004 (dev) |
| R-CI-05 | dev | 0.167 | G-C1 (grounded) | 0.179 | R0-013 (dev) |
| R-CF-01 | dev | 0.167 | R0-057 (test) | 0.091 | R0-057 (test) |
| R-CF-02 | test | 0.125 | R0-001 (dev) | 0.136 | R0-001 (dev) |
| R-CF-03 | dev | 0.226 | G-C3 (grounded) | 0.238 | G-C3 (grounded) |
| R-CF-04 | test | 0.242 | G-C4 (grounded) | 0.261 | G-C4 (grounded) |
| R-CF-05 | dev | 0.243 | R0-006 (dev) | 0.208 | R0-006 (dev) |
| R-FP-01 | test | 0.100 | R0-053 (dev) | 0.118 | R0-005 (dev) |
| R-FP-02 | test | 0.135 | R0-050 (dev) | 0.062 | R0-027 (dev) |
| R-FP-03 | test | 0.407 | R0-063 (dev) | 0.368 | R0-063 (dev) |
| R-FP-04 | dev | 0.179 | R0-057 (test) | 0.148 | R0-057 (test) |
| R-FP-05 | dev | 0.184 | R0-064 (dev) | 0.156 | R0-062 (dev) |
| R-FP-06 | test | 0.158 | G-A3 (grounded) | 0.095 | G-A4 (grounded) |
| R-RF-01 | dev | 0.118 | R0-025 (test) | 0.050 | R0-047 (test) |
| R-RF-02 | test | 0.167 | R0-027 (dev) | 0.154 | R0-059 (dev) |
| R-RF-03 | dev | 0.200 | R0-022 (test) | 0.231 | R0-010 (test) |
| R-RF-04 | test | 0.167 | G-A3 (grounded) | 0.083 | G-I6 (grounded) |
| R-RF-05 | test | 0.207 | R0-064 (dev) | 0.111 | R0-040 (dev) |
| R-RF-06 | test | 0.250 | G-I1 (grounded) | 0.214 | R0-059 (dev) |
| R-IS-01 | dev | 0.357 | G-I2 (grounded) | 0.333 | G-I2 (grounded) |
| R-IS-02 | test | 0.162 | G-C1 (grounded) | 0.125 | R0-015 (test) |
| R-IS-03 | test | 0.185 | R0-011 (dev) | 0.105 | R0-011 (dev) |
| R-IS-04 | test | 0.267 | G-I8 (grounded) | 0.222 | G-I8 (grounded) |
| R-IS-05 | test | 0.217 | G-A5 (grounded) | 0.071 | R0-039 (test) |
| R-IS-06 | dev | 0.286 | R0-011 (dev) | 0.200 | R0-001 (dev) |
| R-SC-01 | dev | 0.304 | R0-011 (dev) | 0.235 | R0-011 (dev) |
| R-SC-02 | test | 0.286 | G-I1 (grounded) | 0.222 | G-I2 (grounded) |
| R-SC-03 | dev | 0.417 | R0-060 (dev) | 0.467 | R0-060 (dev) |
| R-SC-04 | test | 0.471 | R0-009 (dev) | 0.545 | R0-009 (dev) |
| R-SC-05 | dev | 0.400 | G-I5 (grounded) | 0.455 | R0-058 (dev) |
| R-SC-06 | test | 0.250 | G-C2 (grounded) | 0.308 | G-C2 (grounded) |
| R-SC-07 | test | 0.219 | G-A2 (grounded) | 0.190 | G-A2 (grounded) |
| R-SC-08 | dev | 0.261 | R0-010 (test) | 0.333 | R0-010 (test) |
| R-SC-09 | test | 0.375 | R0-032 (dev) | 0.200 | R0-032 (dev) |
| R-SC-10 | dev | 0.286 | R0-008 (dev) | 0.222 | G-I1 (grounded) |
| R-SC-11 | test | 0.269 | G-A3 (grounded) | 0.222 | G-I2 (grounded) |
| R-SC-12 | test | 0.188 | R0-032 (dev) | 0.143 | G-I4 (grounded) |

Highest similarity to a retrieval-v0 test or grounded-v0 question: R-SC-03 vs G-R0-060 (0.467).

Highest similarity overall: R-SC-04 (0.545).

## Caveats

- Facts overlap with retrieval-v0/grounded-v0 by construction (same fixed corpus); only questions are new. Several multi-part items reuse a fact that a retrieval-v0 test item asks about in a single-fact form.
- Alternates added here are single-reviewer; retrieval-v0's were dual-judged.
- `router_expectation` is judged from the question text alone; reformulation items that look like single lookups are labelled `standard` even though research may recover a missed first pass.
