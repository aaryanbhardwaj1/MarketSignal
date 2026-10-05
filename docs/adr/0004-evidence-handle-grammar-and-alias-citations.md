# ADR-0004: Evidence-handle grammar and run-local `[E#]` alias citations with a streaming hold-back gate

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** **Phase 1 implemented** (grammar, strict parser, builder, resolver, workspace check); Phase 3 (alias layer, hold-back gate, verifier)
- **Related:** plan §10, §10.1, §16, §21, §3.1, §24; ADR-0001, ADR-0003; approved deviation D2

## Context

Every claim must cite evidence that backend code, not the model, can resolve to exact text. Spec §11 requires handles to be deterministic, unique, resolvable, stable, tied to workspace and source, safe to render, and rejected when invalid.

Asking the LLM to reproduce full handles verbatim has known failure modes: mistyped or invented handles, wasted output tokens on long strings, and the temptation to "repair" near-misses with fuzzy matching, which would turn a fabrication into a confident wrong citation.

Answers stream as a draft before verification (§21). A citation must never render as a chip until it is known to point at pack evidence, and model output is untrusted (prompt injection can try to plant a citation or markdown).

## Decision

**Canonical handle grammar** `WORKSPACE/SOURCE@vVERSION:LOCATOR`, e.g. `NORTHSTAR/SURVEY-2026@v1:R185`:

```
handle = ws "/" src "@v" ver ":" loc                    ; total length ≤ 96
ws     = [A-Z][A-Z0-9]{1,15}                            ; immutable workspace code
src    = [A-Z0-9]{1,12} ( "-" [A-Z0-9]{1,12} ){0,5}     ; immutable per-workspace source code
ver    = [1-9][0-9]{0,3}
loc    = unit ( "." unit ){0,3} | "AQ" HEX{12}          ; structural | computed analytics result
unit   = kind [1-9][0-9]{0,6};  kind = SL|SH|P|B|S|N|R|Q|T
```

- Pure function of workspace code, source code, version and structural locator; `AQ` = `sha256(normalized_spec ‖ source_version_id)[:12]`.
- Alphabet `[A-Z0-9v/@:.-]` (lowercase `v` only in the `@v` marker): no markdown or HTML can be expressed. `unique(workspace_id, handle)` in the database.
- One resolver (§16): parse → workspace must match scope (else NOT_FOUND, revealing nothing) → `source_versions` (purged → `410 SOURCE_DELETED`) → `parent_chunks` or `analytic_results`. Malformed → `MALFORMED_HANDLE`; **never fuzzy-matched**.

**Alias layer.** At pack time each item gets `E1..En` for this run only (pack ≤ 12 items). Evidence is delimited as `<evidence alias="E3" class="…">` with server-set attributes. The model may emit only `[E\d{1,2}]`.

**Hold-back gate.** Streamed text is held from a `[` only while it can still become `[E\d{1,2}]`, so at most 4 characters are held. A valid alias emits `citation {alias, handle, …}` on first use; an unknown alias is removed before emission and raises a `warning`.

**Verification** (deterministic, answer contract §3.1): every alias maps to a pack handle; numbers appear in cited evidence; uncited non-heading sentences are dropped or tagged `[inference]`; at most 20 citations. On structural failure: repair, then one `draft_reset` regeneration if time allows, else evidence-only. `final` carries canonical handles and supersedes the draft.

## Approved spec deviation

- **Spec position (D2):** "Answer generator must reference handles exactly."
- **Approved change:** the generator cites per-answer aliases `[E1]..[En]`, mapped deterministically to canonical handles before storage or rendering.
- **Approval requirement:** aliases are **strictly run-local** and are **never persisted as evidence identities**. Before any final storage or rendering, every alias must resolve deterministically to a canonical handle from the **current run's** evidence pack. An alias that does not resolve is removed and recorded as a warning; it is never guessed.
- **How the requirement is met:**
  - The alias map is built from the current run's pack and lives only in that run's generation context; a regeneration after `draft_reset` reuses the same pack. Aliases restart at `E1` every run, and earlier turns are referenced by canonical handle in conversation state, never by alias.
  - `messages.content`, `messages.citations`, `hypothesis_evidence`, briefs and answer-cache entries store canonical handles only.
  - `run_events` (replay log, 30-day retention) contains draft `token` text with alias markers and `citation` events that bind each alias to its canonical handle *for that run*. These are display records for SSE replay, scoped by `run_id`, and are never read as evidence identities.
  - Chips render only after a `citation` event, i.e. after deterministic resolution against the pack.
- Approved 2026-10-05.

## Alternatives considered

- **Model emits canonical handles directly (spec position).** Invented or mistyped handles must be rejected after the fact; more output tokens; no streaming-safe point to validate.
- **Native provider citations** (Anthropic `search_result` blocks with `citations.enabled`). GA, guarantee valid pointers and return `cited_text` spans. Not primary because: the core trust primitive should not depend on one vendor behind a provider adapter; FakeLLM and offline eval must behave identically; citations attach to text blocks rather than inline positions; they cannot be combined with structured outputs. They also do not force every claim to be cited, so our verifier is needed either way.
- **Opaque UUIDs as evidence ids.** Unique, but not human-verifiable, not deterministic across re-ingest, and not tied visibly to workspace and source.
- **Buffer until `final` (no streaming).** Removes the need for a gate but leaves 8–15 s of silence.

## Tradeoffs accepted

- An extra mapping layer between model output and stored answers.
- The user can briefly see a draft sentence that verification later removes; the draft is labelled "Draft — verifying…" and chips stay pending until validated.
- The grammar is fixed; a new locator kind is a grammar change with migration of tests and fixtures.
- Vendor-native span extraction is not used; span highlighting comes from anchor offsets (ADR-0003).

## Consequences

**Positive:** fabricated handles are impossible by construction (the model can reference only pack items); verification is a dictionary lookup; handles render safely; stored answers remain resolvable after the run ends.

**Negative:** the gate, alias map and verifier are custom code that must be exhaustively tested; a two-digit alias limit is fixed (ample for a ≤ 12-item pack).

**Follow-ups:** optional Phase 7 A/B of alias vs native citations on citation precision, latency and tokens.

**Verification**
- Grammar: Hypothesis round-trip `format(parse(h)) == h`; fuzzing (arbitrary strings never raise unexpectedly and never resolve); length and alphabet limits.
- Resolver ordering, including tombstones and foreign-workspace handles → NOT_FOUND.
- Alias gate with randomized delta splits; verifier tests (sections, numeric faithfulness, inference tags); SSE event-order contract test (`final` before `done`, `done` last).
- To add with the component: persisted `messages`, citation cards, hypothesis links and cache entries contain no `[E\d+]` evidence identities.
- Deterministic CI-gated metrics: citation validity 100%, citation-in-pack 100%, numeric faithfulness, finding-citation coverage.
- Injection suite includes a citation-hijack attack goal (Phase 8).

## Implementation notes (Phase 1, 2026-10-05)

- **Grammar.** `WS/SOURCE@vN:LOCATOR`, alphabet `[A-Z0-9v/@:.-]` (the lowercase `v` is the version marker), maximum 96 characters.
  - Units: `SL SH P B S N R Q T`.
  - Computed handles: `AQ` + 12 hex characters (reserved for Phase 5).
  - Earlier drafts of this ADR and of the plan left the `v` out of the alphabet. That was corrected when the grammar was implemented.
- **Parsing.** `parse_handle` is strict. It rejects lowercase workspace, source or unit text, leading zeros in versions and indices, lowercase hex in computed handles, unknown units, trailing characters (such as Markdown link injection) and over-length input. `parse_rendered_handle` accepts the bracketed display form.
  - 51 unit tests cover the parser, including property-based round-trips (Hypothesis).
  - The generator guards raw length *before* constructing a handle. An early version produced over-length handles and hid failures.
- **Workspace check.** `require_workspace` compares the handle's workspace prefix with the route's workspace. A mismatch is reported as **404 `EVIDENCE_NOT_FOUND`**, the same as an unknown handle, so a handle never reveals that another workspace exists. RLS would hide the row anyway; the check makes the outcome explicit and cheap.
- **Resolver outcomes:** malformed → 400 `MALFORMED_HANDLE`; unknown or foreign → 404; purged source → 410 `SOURCE_DELETED` with tombstone; otherwise 200 with exact parent text, `content_hash`, locator and label, version status (`is_latest`, `latest_version`), provenance, neighbouring excerpts, child spans and optional highlight.
- **Verified on the seeded system:** malformed 400, unknown locator 404, unknown version 404, foreign prefix 404, and a live purge turning 200 into 410.
