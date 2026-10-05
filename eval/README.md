# Evaluation

Retrieval evaluation for MarketSignal (plan §26–27, ADR-0013). The harness lives in `backend/src/marketsignal/evaluation/` and is run with `python -m marketsignal.evaluation`. Phase 2 uses no LLM judge.

## `datasets/retrieval-v0/`: the Phase 2 curated retrieval set

| File | What |
|---|---|
| `items.json` | 65 curated items: question, workspace, category, required fact ids, accepted alternates. **The only hand-maintained file.** |
| `frozen.json` | Output of `freeze`: satisfying parent handles and content hashes per fact, split, leakage group, overlap hardness, hard negatives, and a manifest pinning the dataset to `items_sha256`, `corpus_sha256` and `ledger_sha256` |
| `authoring-fact-digest.json` | The anchor-free fact digest the question writers worked from |
| `authoring-pool.json` | All 71 drafted items, with each critic's verdict and reason |
| `alternates-decisions.json` | Relevance decisions for other parents that contain a fact's surface forms (two independent judges, accepted only if both agree), plus the mechanical prefilter log |
| `alternates-review.json` | Candidates still awaiting a decision; must be `{}` before evaluation |

### How the items were made

1. **Fact digest.** A digest of the fact ledger was produced **without anchor text**: no planted sentences, no rendered documents, no retrieval code.
2. **Drafting.** Four independent writer agents, one per category group, drafted 71 questions from the digest alone. The rules were:
   - semantic paraphrases share at most 3 consecutive words with the fact statement;
   - keyword items hinge on an exact token;
   - versioning items target only the newest fact;
   - distractor facts are never required.
3. **Critique.** One adversarial critic agent per batch checked answerability, uniqueness against the other facts, category fit and naturalness, returning keep, fix or reject. Result: 63 kept, 8 fixed, 0 rejected.
4. **Curation.** The pool was cut to 65 by dropping 6 near-duplicates. Paraphrase pairs that test the same fact as a keyword query and as a semantic query were kept on purpose.
5. **Freezing.** `freeze` located every planted anchor in exactly one active parent.
6. **Alternates.** Other parents containing all of a fact's surface forms were judged separately: 16 pairs, two judges each, unanimous on every pair. 10 were accepted and 6 rejected.
7. **Split.** Dev/test is 70/30, **grouped** by union-find over shared facts, ledger-related facts (contradiction, superseded and distractor pairs) and shared parents, then stratified by category. The result is 44 dev / 21 test items in 40 groups.

All of this happened **before any retrieval run**. Provenance is `llm_draft_agent_reviewed`, and **human review by the project owner is pending**.

### Rules

- **Dev** is for tuning. **Test** is frozen: `run --split test` is refused without `--milestone "<reason>"`, and each test run is appended to `test-split-log.jsonl`.
- **Recorded runs** (baselines and every Phase 2 iteration) live in `baselines/` and are never regenerated after later changes. `reports/` is gitignored scratch output.
- **Integrity.** `integrity` checks, against the ingested corpus, that:
  - every handle resolves through the production resolver;
  - each parent still contains its anchor;
  - content hashes match;
  - the dataset is pinned to the current corpus, ledger and items;
  - no fact or parent leaks across dev and test.

  The offline half also runs in the unit tests.

## Metrics

Every arm maps child hits to **distinct parents** (first occurrence wins) before scoring.

- **recall@k:** the share of an item's required facts with a satisfying parent in the top k.
- **hit@k:** at least one required fact satisfied in the top k.
- **MRR:** reciprocal rank of the first satisfying parent. **recall@20** is Recall@pool.
- **Intervals:** Wilson 95% CIs for hit rates, percentile bootstrap (10,000 resamples, fixed seed) for recall and MRR.
- **Paired comparisons:** exact McNemar for hit@k, paired bootstrap for ΔMRR and Δrecall@10.
- **Overlap hardness:** each item's question is scored against its anchors with a retriever-independent normaliser. Bins: low < 0.34 ≤ mid < 0.67 ≤ high.
