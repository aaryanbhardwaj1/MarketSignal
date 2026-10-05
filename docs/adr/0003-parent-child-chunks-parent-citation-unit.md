# ADR-0003: Parent/child chunking; the parent is the citation unit; parents immutable per version

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** Planned — Phase 1 (ingestion, handles, resolver); anchor propagation completed in Phases 2–3 (this ADR is updated with measurements when the component is built)
- **Related:** plan §9, §4, §4.2, §4.3, §16, §26, §27; ADR-0001, ADR-0002, ADR-0004; approved deviation D1

## Context

Two needs pull chunk size in opposite directions:

- **Retrieval** wants small, focused units: an embedder with a 512-token limit, a cross-encoder window, and lexical scoring that is diluted by long text.
- **Citation** wants stable, human-verifiable units. A consultant checks "slide 6", "row 185", "p.4 ¶2", not "window 3 of 7".

If citations point at retrieval windows, every chunk-size tuning run moves boundaries and orphans stored citations, hypothesis links and gold labels (`satisfied_by` handles). Gold labels must survive tuning or the evaluation measures label drift instead of retrieval quality.

Structured files add a second problem: one child per spreadsheet row floods the candidate pool with numeric rows that semantic search cannot meaningfully rank.

## Decision

**Parents** are structure-derived citation units; **children** are internal retrieval windows.

- **Parent units by format:** PDF paragraph group within one page; DOCX heading section or interview Q&A pair; PPTX slide (notes separate); XLSX/CSV one row plus one table-summary parent per sheet; MD/TXT heading section. Parents never cross a page, slide, row or Q&A boundary; cap 800 tokens, split at paragraph/sentence boundaries into consecutive blocks.
- **Narrative children:** 192-token windows, 32-token overlap, inside one parent, counted with the embedder's tokenizer. Dense input gets a contextual header (`{source title} › {heading path}`).
- **Rows:** a row with free text gets one child (`{table} | {context col=val, …} | {free-text col}: <verbatim>`); a purely numeric row gets a parent only (resolvable, used by analytics, not a retrieval unit); each table summary gets one embedded child.
- **Lists** stay whole in one parent when they fit; larger lists share `list_group_id`.
- Child ids are internal (`parent_handle#w{n}`) and never appear in answers. Each child stores `char_start`/`char_end` into its parent's text.
- **Retrieval ranks parents** (ADR-0002). Generation receives parent text, or a window centred on the anchor child when the parent exceeds its per-item budget.
- **Immutability per version:** once a version is ready its parents never change. A reindex for `chunking_policy_version` or `embedding_model` rebuilds only children, embeddings and tsv. A `parser_version` or `structure_version` change mints a **new version over the same bytes** (`reason=reindex`); the old version stays resolvable. `parent_content_hash` is stored with every citation so drift is detectable.
- **Exception — purge:** privacy wins over immutability. A purge deletes parents, children, embeddings and blobs and leaves a tombstone; the handle resolves to `410 SOURCE_DELETED` (§4.3).

## Approved spec deviation

- **Spec position (D1):** `evidence_handle` lives on `child_chunks`.
- **Approved change:** cite **parents** (structure-derived units); children are internal retrieval windows.
- **Approval requirement:** child-anchor metadata and character offsets (`char_start/char_end` into the parent) are preserved through **retrieval traces, the evidence pool, the pack, and stored citation cards**. Retrieval therefore stays child-granular, and the exact supporting span can be highlighted and evaluated, while the citation points to the stable parent.
- **How the requirement is met:**
  - `retrieval_traces.stages` records `(child_id, parent handle, rank, score, anchor)` per stage; collapse keeps the best-scoring anchor child.
  - Retrieval tool output carries the anchor: `EvidenceHit` includes `anchor_child_id`, `anchor_char_start` and `anchor_char_end` (plan §18, ADR-0006), so the anchor reaches the agent's evidence pool through `structured_content`.
  - Evidence-pool and pack items carry the anchor child id and its offsets (ADR-0007); the pack scores unscored items and centres oversized parents on the anchor.
  - Stored citation cards (`messages.citations`) include the anchor child id, `char_start`, `char_end` and `parent_content_hash`.
  - The evidence viewer returns `highlights[]` for a given `run_id`.
- Approved 2026-10-05.

## Alternatives considered

- **Cite children (spec position).** Most precise span, but unstable: chunk tuning orphans handles, citations and gold labels.
- **Cite whole documents.** Stable but useless provenance; the user cannot verify a claim.
- **Single-level fixed-size chunks.** Simplest; inherits the instability of child citations and ignores document structure.
- **Mutable parents re-derived in place on reindex.** Avoids version churn, but a handle could re-point to different text, breaking stored answers and hypothesis links.
- **One retrieval child per numeric row.** Floods the pool; numeric questions go to the analytics tool instead.

## Tradeoffs accepted

- A citation can cover more text than the exact supporting sentence; the highlighted anchor span narrows it in the UI.
- Two levels cost more storage and more ingestion code than flat chunks.
- Parser or structure changes create new versions, which bumps the corpus version and invalidates the answer cache.
- Purely numeric rows are reachable only through analytics or keyword search, not through `search_evidence`.

## Consequences

**Positive**
- Chunk size can be tuned in Phase 7 without touching handles, stored answers or gold labels.
- Citations point at units a consultant can verify; the anchor span still shows *which* sentence matched.
- Retrieval keeps child-level precision and parent-level fusion (ADR-0002).

**Negative**
- Anchor metadata must be threaded through traces, pool, pack and citation cards; any stage that drops it silently breaks highlighting.

**Follow-ups**
- A span-level evaluation that uses the stored anchor offsets (for example, whether the cited anchor span contains the fact's planted anchor sentence), defined in EVALUATION.md in Phase 7.

**Verification**
- Unit: parent and child builders, row serialization, locators, list grouping.
- Ingest health check on each not-yet-active version: a sampled child's handle resolves to parent text containing that child's text.
- Gold integrity (CI): every `satisfied_by` handle resolves and its parent text contains the anchor or a surface form; each anchor matches exactly one active parent; `content_hash` matches.
- To add with the component: a reindex with a new `chunking_policy_version` leaves every parent handle and `content_hash` unchanged; a contract test that a stored citation card's `char_start/char_end` slice of the parent equals the anchor child's text; a contract test that the anchor offsets survive tool output → evidence pool → pack → stored citation card.
- Integration: purge makes the handle return 410 and removes the canary text everywhere.
