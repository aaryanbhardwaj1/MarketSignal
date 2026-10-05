# ADR-0013: Evaluation methodology: world model, frozen fact ledger, deterministic CI gates, judge calibration and statistics

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** Phase 1 implemented: world model, deterministic seed generator, fact ledger (111 facts), real-API seeding and anchor census. Phase 2: `freeze-gold`, gold v0, retrieval runner, CI smoke. Phase 7: gold v1, calibration, generation metrics.
- **Related:** plan §0.3 (D4), §7, §26, §27, §29, §30, §35, §38; ADR-0002 (hybrid retrieval), ADR-0003 (parent is the citation unit), ADR-0004 (evidence handles), ADR-0012 (embeddings), ADR-0015 (modes and the agent ablation), ADR-0017 (fictional corpus), ADR-0019 (testing strategy); approved deviation D4

## Context

The project's claims (hybrid beats dense-only, reranking helps, the agent is worth its cost, answers are grounded) are only credible if they are measured. That raises several problems:

- **Circularity.** A synthetic corpus written by the same process that writes the questions inflates metrics.
- **Label drift.** Gold labels tied to chunk ids break whenever chunking is tuned.
- **CI flakiness.** HNSW graph construction is non-deterministic and LLM output varies, so gates on either would be flaky.
- **Judge error.** An LLM judge has unknown error rates unless it is calibrated, including on negatives.
- **Small n.** Gold sets of about 40–120 items make small deltas statistically meaningless.
- **Late gold sets.** The spec places gold sets in Phase 7 and the seeded demo in Phase 9, yet its own Phase 2 requires a scored comparison against a dense-only baseline.

## Decision

**1. World model → corpus → fact ledger.**
- `seed_data/world_model.yaml` defines segments, pain points with prevalence, fictional competitors' positioning, product/channel/category metrics, planted contradictions, superseded values and gaps.
- Template generators render byte-reproducible documents in every format (PDF, DOCX, PPTX, XLSX, CSV, MD).
- A **fact ledger** maps each `fact_id → (source_code, anchor, surface forms)`. The anchor is a unique planted sentence or a row key. The surface forms are value + unit + entity, plus a few alternate spellings.

**2. Freeze against reality** (`ms-eval freeze-gold`).
- Ingest a fresh seed through the **real pipeline**.
- Locate the active parent(s) containing each anchor and fill `satisfied_by` with **parent handles**. Labels therefore survive child-size tuning (ADR-0003).
- Surface-form matches outside the hinted source are recorded for review, never auto-added, so distractors are never labelled relevant.
- The manifest records `parser_version`, `structure_version` and `corpus_sha256`.

**3. Question independence.**
- Questions are written from the world-model fact record only, without seeing the rendered text, and provenance is recorded.
- Each item gets a retriever-independent **lexical-overlap hardness score** (low/mid/high bins). Every ablation is reported per bin.

**4. Datasets and splits.**
- Gold v0: about 40 curated items by the end of Phase 2. Results are directional, with CIs.
- Gold v1: about 120 curated items by Phase 7. This is the gate set.
- A ledger-generated **ablation set** of about 250 queries, labelled easier and never used for gates.
- **Dev/test 70/30, grouped by fact_id or source group**, so no planted fact appears in both splits. Tuning uses dev. The frozen config runs once on test at milestones.
- A **fresh-seed holdout** (Phase 7) re-samples the world model with new names and numbers to measure overfitting.

**5. Metrics.**
- Retrieval: Recall@k/hit@k over grade-2 facts, MRR, nDCG@10, Recall@pool (fused top-20), Recall@pack, agent evidence recall from traces, and class coverage. Every arm maps child lists to parents and dedupes by first occurrence before scoring.
- Deterministic grounding: citation validity, citation-in-pack, numeric faithfulness and finding-citation coverage.
- Judge-based: citation support precision, faithfulness and answer relevancy.
- Behavioral: answer, qualify, abstain or resist; injection with exposure conditioning and k = 5; isolation via canaries.

**6. CI gates only on deterministic metrics.**
- The retrieval smoke runs on the full seed and dev-split queries with **exact search**, local ONNX models and a cached embedding file.
- Floors are baseline − max(measured run-to-run noise, paired MDD). The run also fails on newly failing items from a pinned canary subset.
- Baselines are generated in CI on the same runner image and change only in a PR that includes the diff report.
- Gold integrity checks: every handle resolves and contains its anchor or a surface form; each anchor maps to exactly one active parent; hashes match the manifest; no unreviewed `llm_draft` items.

**7. Judge calibration.**
- The judge is `claude-opus-5-5`, a different model from the generator, giving binary (plus partial) verdicts in strict JSON.
- The calibration set has about 100–120 claim/passage pairs, roughly 50/50 supported vs unsupported. Negatives come from the ledger (distractor numbers, swapped entity or segment, superseded values), and about 40 pairs are hand-labelled from real outputs.
- Reported: sensitivity and specificity with Wilson CIs, and a flip rate across 3 re-judges. Measured citation precision is always shown next to the judge's false-positive rate.

**8. Statistics.**
- Wilson 95% CIs for rates; bootstrap CIs for MRR and nDCG.
- **Paired tests on the same items:** exact McNemar for hit@k, paired bootstrap for continuous metrics.
- EVALUATION.md states the **minimum detectable difference** at the current n (about 15 points at n ≈ 100). Smaller deltas are reported as "not distinguishable".
- Cells with n < 10 are reported as k/n. The test split is never broken down by category.

**9. Tuning protocol.** At least 2 documented iterations. Each states a hypothesis beforehand from a dev failure analysis, makes one change, and is compared paired on dev.

## Approved spec deviation

- **Spec position:** the seeded demo is built in Phase 9 and the gold sets in Phase 7.
- **Approved change (D4):** the seed corpus and gold v0 move to Phases 1–2.
- **Rationale:** spec Phase 2 already requires a scored gold set compared against a dense-only baseline, which is impossible without a seeded corpus and gold labels. Building them early also means the D5 tuning iterations come from real measured failures.
- **Approval requirement:** none beyond the change itself. Gold v1 (about 120 items) and the full quality gates remain in Phase 7.
- **Approved 2026-10-05.**

## Alternatives considered

- **Hand-labelled chunk ids.** Labels break on every chunking change and cannot be integrity-checked. Not chosen.
- **LLM-generated questions over rendered text.** Cheap and large, but circular: questions inherit the documents' wording and inflate lexical and dense recall. Not chosen.
- **Framework metrics (RAGAS and similar) as a dependency.** The definitions are reused and implemented in-house, so every number is explainable and versioned in `config_hash`.
- **Gating CI on judge or e2e metrics.** Non-deterministic and needs a key in CI. These run manually or nightly (`eval-full.yml`).
- **Gating on ANN search.** HNSW randomness would make the gate flaky. ANN recall against exact is reported instead.
- **Random (ungrouped) dev/test split.** Leaks planted facts across splits and overstates generalization.

## Tradeoffs accepted

- The corpus is synthetic, so absolute numbers do not transfer to real corpora. Distractors, contradictions, hardness bins and the fresh-seed holdout bound but do not remove the optimism.
- At n ≈ 100 only large effects (about 15 points) are detectable. Many ablation deltas will honestly read "not distinguishable".
- Same-family judge bias is not excluded. Calibration with negatives and a reported FPR make it visible.
- The adopted spec §20.4 gates are targets, not results. They include Recall@10 ≥ 0.85 on the curated test split after tuning, citation precision ≥ 0.90 (judge-dependent), abstain/qualify recall ≥ 0.90 and over-refusal ≤ 0.10. If the corpus makes a gate unrealistic, the reason and an evidence-based replacement are documented.

## Consequences

**Positive**
- Every claim in the engineering report is reproducible from a `config_hash` (retrieval config, prompts, models and efforts, dataset version, corpus sha256, git sha).
- Before/after tuning iterations are defensible under paired statistics.

**Negative**
- Meaningful up-front cost in Phases 1–2: generator, ledger, `freeze-gold`, runner.
- Gold integrity checks become a CI dependency.

**Follow-ups**
- Phase 2 report: dense-only vs lexical-only vs hybrid vs + rerank, with CIs and overlap bins.
- Phase 7: gold v1, judge calibration, the agent-vs-single-pass ablation (ADR-0015) and the fresh-seed holdout.

**Verification**
- CI steps 5 (retrieval smoke with floors) and 6 (gold integrity) in `ci.yml`.
- The judge calibration report (sensitivity, specificity, flip rate).
- Per-iteration tuning reports.
- The holdout gap against dev.

## Implementation notes (Phase 1, 2026-10-05)

- **Inputs.** `seed_data/world_model.yaml` defines the fictional companies, segments, products and planted facts. `seed_data/generator/` renders the corpus deterministically: same world model, same bytes, checked by `make seed-check`.
- **Corpus.** 30 uploads across all seven formats:
  - Northstar: 24 uploads, including a v1 → v2 update of `GENZ-TRENDS`;
  - Southpeak: 6 uploads.
  - The generated files are committed byte-exact; `.gitattributes` marks them `-text` so CRLF CSVs are not normalised.
- **Fact ledger.** `seed_data/fact_ledger.json` holds 111 facts.
  - Each fact has an anchor: an exact sentence, or a row (`key_column`, `key_value`, `value_column`, `value`) with an optional sheet. It also has a statement and its source.
  - The ledger includes superseded pairs (v1 → v2), distractors and an injection carrier for later security evaluation.
- **Seeding** goes through the real upload API (`scripts/seed.py`), the same path user documents take.
- **Anchor census** (`scripts/verify_phase1.py`). All 111 anchors are located in **exactly one** parent of the ingested corpus: 0 missing, 0 ambiguous. This is the basis for Phase 2's `freeze-gold`, which will write the resolved handles into gold v0.
