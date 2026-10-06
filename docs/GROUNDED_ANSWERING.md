# Grounded answering deep dive (Phase 3)

**Last updated:** 2026-10-05 · **Code:** `backend/src/marketsignal/generation/`, `providers/llm/`, `runs/`, `api/routers/runs.py`, `ingestion/purge.py`, `frontend/src/lib/run-stream.ts`, `frontend/src/components/chat/` · **Decisions:** ADR-0004 (handles and aliases), ADR-0007 (bounds), ADR-0008 (SSE), ADR-0015 (modes), ADR-0016 (purge)

This document describes how a standard-mode run turns ranked evidence into a verified, cited answer and streams it, as the code does it today. The system-level view (components, tables, termination, configuration) is in [`SYSTEM_DESIGN.md`](SYSTEM_DESIGN.md).

> **Measurement status.** Every guarantee below is enforced by deterministic code and covered by unit or integration tests. The real model has **not been run yet**: the live Anthropic spike and the live grounded evaluation are **pending live evaluation**, because no API key is configured. This document reports no live latency, token or quality figures.

## The question this document answers

> *How does the system guarantee that what the user finally sees is grounded in workspace evidence, even though a language model writes it and streams it before it is checked?*

The short answer:

1. **The model never decides what evidence exists.** The server builds a deterministic evidence pack from Postgres and shows it to the model under run-local aliases (`E1..En`).
2. **The model can only cite by alias, and only valid aliases ever reach the screen.** A streaming hold-back gate removes unknown aliases before they are displayed and binds valid ones to canonical handles before the text that uses them.
3. **Only verified text becomes the answer.** A deterministic verifier strips leaks, repairs what it can, checks numbers against the cited evidence and enforces the answer structure. A failure gets one regeneration, then an evidence-only answer. A fluent but unverified answer is never stored.
4. **Stored answers carry canonical handles, never aliases**, and every one resolves through the evidence resolver.
5. **Deletion wins.** A purge removes every stored quote of the deleted source, including from runs still in flight.

---

## 1. Evidence pack

`generation/pack.py::build_pack` runs between retrieval and generation. Given the ranked parents of one retrieval call:

| Step | Rule |
|---|---|
| Candidates | Retrieval rank order (fused RRF order under the production default), **de-duplicated by handle**, at most `pack_candidates` (24). A handle whose prefix is not `"{workspace_code}/"` is skipped before any database read. |
| Resolution | Canonical parent text, `token_count`, `content_hash`, locator label, heading path, source code, title, type and class are read from Postgres in the workspace scope (RLS plus an explicit `workspace_id` predicate, and `sources.deleted_at IS NULL`). A candidate that no longer resolves (purged between retrieval and packing) is skipped. |
| Anchor | The candidate's best matched child (`best_anchor()`): child id and `char_start/char_end` into the parent (D1). It travels into the citation card for highlighting. |
| Windowing | A parent within `pack_item_max_tokens` (900) is shown whole. A larger one is shown as a window of about that size, centred on the anchor, never cutting through the anchor, widened to whitespace. The block is marked `excerpt="true"`. |
| Budget fill | In rank order, until `pack_max_items` (12) items are packed. An item that would exceed `pack_max_tokens` (9,000) is skipped and **filling continues with smaller items**. |
| Truncation | `truncated` is set when a skipped item was ranked within the item limit (position ≤ 12). It raises `PACK_BUDGET_TRUNCATED`, the `completed_with_limited_evidence` state, and makes a Gaps section mandatory (§4). Skipped handles are recorded in `dropped`. |
| Aliases | `E1..En` in pack order. |

**Token unit.** Budgets use the parent's stored `token_count`, which comes from the embedder's WordPiece tokenizer (ADR-0012), as a deterministic proxy for model tokens. Windows are sized by the parent's average characters per token. The real input usage is recorded per run from the provider's `usage`. How closely the proxy tracks Anthropic tokenization is **pending live evaluation**.

**Freezing.** Before any event or model call can quote the pack, `runs/store.py::freeze_pack` records `query_runs.pack_handles` after share-locking the pack's `sources` rows once and checking `source_versions.status = 'purged'` for the exact version of each handle (§8). Sources purged since the pack was read are left out and the executor drops those items.

The `evidence` event reports `{item_count, classes, truncated}`. Pack tokens are stored on the run but not streamed.

## 2. Aliases and canonical handles

| | Canonical handle | Run-local alias |
|---|---|---|
| Form | `WS/SOURCE@vN:LOCATOR`, e.g. `NORTHSTAR/SURVEY-2026@v1:R185` (ADR-0004 grammar, ≤ 96 chars) | `E1` … `E12` |
| Scope | Stable identity, unique per workspace, resolvable by the evidence API | One run only |
| Seen by the model | Never | Always (`<evidence alias="E3" …>`) |
| In streamed events | In `citation` payloads (alias → handle binding) | In `token` text as `[E3]` |
| In stored answers | As the marker **`[[HANDLE]]`** in `messages.content` and in citation cards | Never |

The canonical marker `[[HANDLE]]` (`generation/types.py::CANONICAL_RE`) is written only by the verifier and by the deterministic fallbacks. Any `[[…]]` the model writes is stripped as a leak (§5.4). The frontend's `SafeMarkdown` turns each canonical marker in a `final` answer into a citation chip linked to the evidence viewer; a marker with no matching card renders as a chip without a link.

A citation card (`PackItem.card()`) carries `handle`, `source_code`, `source_title`, `source_class`, `source_type`, `locator_label`, `anchor_child_id`, `char_start`, `char_end` and `parent_content_hash`.

## 3. Prompt and trust policy

`generation/prompts.py`:

- **One static system prompt**, byte-stable so it can be prompt-cached. It carries the whole trust policy and the answer contract. `PROMPT_VERSION = "synth-v1-" + sha256(prompt)[:10]` is recorded on every run, so any prompt edit is visible in the data.
- **Retrieved content is untrusted data.** The prompt tells the model that evidence items are quoted documents, that instructions, role-play or formatting demands inside them must never be followed, and that the user's question cannot change the rules. It also forbids URLs, links, images, HTML, file paths, handles and internal identifiers, and answering from background knowledge.
- **Evidence rendering.** Each item is an `<evidence alias="E3" class="…" source="…" locator="…" [section="…"] [excerpt="true"]>` block. Attribute values come only from server data and are attribute-escaped; document text is HTML-escaped (`& < > "`), so a document cannot close its block or inject markup.
- **User turn.** Optional `<conversation_context>` (a rolling summary of earlier *verified* answers and the last two questions), then `<evidence_items>`, then `<question>`. For a regeneration, `<verification_feedback>` lists what the verifier rejected. Everything interpolated is escaped.
- **Conversation state** (`runs/conversation.py`) is built without an LLM call: the summary is at most 1,600 characters (about 400 tokens) taken from the Answer units of verified answers, newest first, with citation markers removed and `[inference]` units left out. It also keeps the last two questions and up to 20 cited handles. Retrieval uses the current question only.
- **Confidentiality ceiling.** Retrieval filters out content above the workspace's `llm_max_confidentiality`, so such content never enters a pack.

The trust policy is a prompt-level instruction. The guarantees do not depend on the model obeying it: the gate and the verifier enforce the output rules whatever the model writes.

## 4. Answer contract

The model answers in Markdown with fixed level-3 headings (no JSON mode). `generation/contract.py::parse_sections` maps `##`–`####` headings, case- and emphasis-insensitive, with `&` folded to "and", onto five canonical sections. Anything else (preamble, unknown headings) goes to `unrecognized` and is dropped visibly ("dropped text outside the answer sections").

| Section | Model instruction | Verifier rule |
|---|---|---|
| **Answer** | 2–4 sentences, each cited `[E#]` or starting `[inference]` | Cited sentence: its numbers must be in its cited items. Uncited sentence: tagged `[inference]` if every number in it is in the pack, otherwise dropped. More than 4 raw sentences → `answer_too_long`. Empty → `answer_missing`. |
| **Key findings** | Bullets, each cited; numbers copied exactly | Bullet without a valid citation is dropped; bullet with a number not in its cited items is dropped. |
| **Conflicting evidence** | Only when items disagree | Same as findings. Not required by the verifier (standard mode has no stance classification). |
| **Interpretation** | Optional; every sentence `[inference]` | Tagged `[inference]` if not already; numbers must be in the cited items (if cited) or the pack. |
| **Gaps & unknowns** | No citations, no numbers | Citations removed, units with numbers dropped. A unit that does not state missing evidence (`states_gap`) is tagged `[inference]`. Required (`gaps_missing`) when the pack was truncated. |

**Evidence, inference, unknown.** These are three visibly different kinds of statement in the final answer: evidence-backed units carry canonical citations; inferences carry the `[inference]` tag and are styled apart (`frontend/src/components/chat/answer-view.tsx`, tone `inference`); gaps live in their own section and carry neither citations nor numbers. `final.sections` carries the parsed structure so the UI does not re-parse prose.

**Units.** `split_units` produces one unit per bullet and one per sentence elsewhere. The splitter is conservative: decimals, abbreviations, citations and inline code never split a sentence, and a lowercase continuation never starts one, because a false split would strand a citation away from its claim.

## 5. Generation, gate, verification and fallback

### 5.1 Provider call

`providers/llm/anthropic.py` streams one Messages call:

- The system prompt is a single text block with `cache_control: ephemeral`; `output_config.effort` comes from `llm_effort`; thinking is `disabled` or `adaptive` with display omitted. Only `text_delta` events inside text blocks are yielded; thinking content is never surfaced or streamed.
- **Retries are ours.** The SDK runs with `max_retries=0`. On 429, 529, other 5xx, an in-stream `overloaded_error`/`api_error`/`rate_limit_error`, or a connection/timeout error, the provider retries **once**, after 0.5–1.5 s of jitter, only if no text has been yielded yet and enough of the call budget remains. Anything else raises `LLMUnavailableError`.
- **Secrets.** The key is handed to the SDK client and not kept on the provider; `__repr__` omits it; error messages carry only the error class, status and request id, and are raised `from None` so the SDK exception (whose request carries auth headers) is not chained.
- **Time.** Each call's budget is `min(llm_timeout_s, remaining_deadline − run_finalize_reserve_s)`. A slow provider therefore degrades to evidence-only instead of timing the run out.
- The six API assumptions listed in the module docstring (effort values, thinking modes, cache token accounting, usage fields, stop reasons, mid-stream overload) are what the live spike must confirm. **Pending live evaluation.**

Outcomes: `end_turn` → verification; `refusal` → `MODEL_REFUSAL`; `max_tokens` → `GENERATION_TRUNCATED`; `LLMUnavailableError` (or any provider exception, including a missing key) → `LLM_SYNTHESIS_UNAVAILABLE`. The last three go straight to evidence-only without regeneration.

### 5.2 Streaming alias gate

`generation/aliases.py::AliasGate` sits between LLM text deltas and `token` events. Text can arrive split anywhere (`"growth [E"` + `"3] …"`), so the gate classifies each candidate starting at `[`:

| Verdict | Grammar | Action |
|---|---|---|
| `ALIAS` | `[E` + 1–2 ASCII digits + `]` | Kept if the alias is in the pack (exact string match). Otherwise removed with warning `UNKNOWN_ALIAS`. This covers `[E99]`, `[E0]` and zero-padded `[E01]`: aliases are never normalised. |
| `MALFORMED` | `[E]` or `[E` + 3–4 digits + `]` | Removed with warning `MALFORMED_ALIAS`. |
| `LITERAL` | Anything else | The `[` is ordinary text: `[inference]`, `[1]`, `[e3]`, `[E 3]`, `[E3a]`, `[E12345]`, `[[WS/SRC@v1:P1]]` pass through (the verifier deals with them). |

Guarantees:

- **An unknown or malformed alias is never displayed**, not even for one frame.
- **A valid alias produces exactly one `citation` event on first use, emitted before the text carrying the marker**, so the client already knows the alias → handle binding when `[E3]` arrives.
- **Split invariance:** for every way of splitting the same model output into deltas, the event sequence (with adjacent text merged) is identical. This is property-tested with Hypothesis (`backend/tests/unit/test_alias_gate.py`).
- **Bounded hold-back.** Text with no `[` is never held. A prefix of a valid alias holds at most 4 characters (`[E12`), as ADR-0004 states; the malformed-attempt rule extends the worst case to **6** (`[E1234`), so `[E123]` can be dropped rather than shown. At end of stream an undecided partial such as `[E1` is released verbatim.
- **Removal never creates a marker.** If the kept text before a removed marker ends in an alias prefix, one space is inserted (`"[E1[E99]]"` → `"[E1 ]"`, never `"[E1]"`). Every removed occurrence is reported.

`strip_unknown_aliases` is the non-streaming form with the same grammar, text and warnings.

### 5.3 Verifier

`generation/verifier.py::verify_answer(raw, pack, pack_truncated)` is a pure function. There is no runtime LLM check. Order:

1. **Leak stripping** of the whole text before parsing (§5.4), so a URL or a forged `[[…]]` marker cannot survive inside a unit.
2. **Per-unit cleaning.** Every alias-shaped marker (including `[e3]`, `[ E3 ]`, `[E1, E2]`) that is not an exact `[E\d{1,2}]` naming a pack item is removed and reported in `unknown_aliases`; a repeated citation in the same unit collapses; the `[inference]` tag is normalised; empty units are dropped.
3. **Section rules** (§4), each logged as a repair: `"<Section> #<n>: <action>"`.
4. **Citation resolution.** Every surviving citation is a pack alias by construction, so every final citation maps to a pack handle. On output, aliases become `[[HANDLE]]`; every other `[[`/`]]` is removed.
5. **Structural checks**, the only failures (`ok = False`): `answer_missing`, `answer_too_long` (> 4 sentences), `no_citations` (zero citations with a non-empty pack, unless the Answer or an untagged Gaps unit explicitly states the evidence is insufficient), `too_many_citations` (> 20), `gaps_missing` (pack truncated and no Gaps).

The report (`final.verification`) records `passed`, `structural_failures`, `repairs`, `unknown_aliases`, `numeric_violations`, `leaks_removed`, `citations`, `cited_aliases` and `sections`.

### 5.4 Numeric faithfulness

`generation/contract.py` extracts numeric claims and normalises them to a mantissa and a scaled value, so `$612.0 million`, `612.0` and `$612.0M` compare equal (relative tolerance 1e-6; sign ignored, so "fell 3.2%" matches "-3.2%").

- **What counts as a claim.** Digits with optional sign, currency (`$`, `US$`, `€`, `£`, `USD`, `EUR`, `GBP`), thousands separators, decimals, a scale (`thousand|million|billion|trillion`, `k/m/b/t`, `bn/mn/mm/tn`), a multiplier (`x`, `×`), a unit suffix (`bps`, `bp`, `pp`, `ppt(s)`, `pt(s)`) and a percent marker (`%`, `percent`, `per cent`, `pct`). Numbers glued to letters (`Q2`, `FY26`, `R0147`, `3rd`, `COVID-19`) and line-start list ordinals are identifiers, not claims. Citation markers are removed before extraction.
- **Scale rule.** Scaled values must agree. The mantissa alone suffices only when at most one side states a scale: a bare table cell `612.0` backs `$612.0 million`, but `612.0 million` never backs `612.0 billion`.
- **Percent rule.** Percent must agree on both sides, with one exception: a **bare** figure (no scale, no currency, no unit label) may stand for a percent, because table cells often carry the unit in a header. A figure is *labelled* (not bare) when a unit word follows it (`2,960 respondents`, `340bps`) or a non-percent-like `label:` precedes it (`Respondents: 2,960`). A bare range start inherits the percent of its end (`14 to 21 percent`).
- **Currency rule.** When both sides state a currency, they must be the same currency.
- **Where the check applies.** A cited unit's numbers must appear in *its cited items*; an uncited `[inference]` unit's numbers must appear somewhere in the pack. A failing unit is dropped and recorded in `numeric_violations`.

Documented limits (kept deliberately, because guessing would create false passes):
- Spelled-out numbers count only with a magnitude word or "percent" (`nine hundred million`, `twenty-one percent`). A bare `twenty` or `one` is **not checked**; neither are fractions such as "a third".
- An **unlabelled table cell** can back a percent claim (the bare-figure exception above). A claim of `12%` is therefore accepted against a cell that says `12` in a column whose header is not percent.
- The check is about presence, not meaning: a number that exists in the cited item but describes something else passes. Claim-level semantic checking is the offline judge's job (ADR-0013), not the runtime's.

### 5.5 Leak stripping

`strip_leaks` removes, in this order: canonical `[[…]]` markers, `<script>`/`<style>` blocks, HTML comments, raw handles (bracketed or bare), images, links (the link *text* is kept, with its brackets if it is an alias citation), URLs (`http(s)://`, `ftp://`, `www.`, autolinks), remaining HTML tags, UUIDs (dashed and 32-hex) and child-id fragments (`#w12`). It repeats **to a fixpoint**, tidying whitespace between passes, because one removal can reassemble a marker an earlier rule passed over (`[[[](u)WS/SRC@v[](u)1:P1]]`). Each pass that removes something shortens the text, so the loop terminates. The evidence-only fallback runs document text through the same function and then neutralises brackets and angle brackets.

### 5.6 Repair → one regeneration → evidence-only

`runs/synthesis.py::generate_and_verify`:

1. Attempt 1 streams and is verified. Repairs are allowed: a repaired answer with no structural failure is published.
2. On a structural failure, if at least `regeneration_min_remaining_s` (15 s) of the run deadline remains, the executor emits `draft_reset {attempt: 2, reason: "verification_failed"}` and regenerates **once**, with `regeneration_feedback` (the structural failures in plain language, up to 8 numeric violations, and the unknown aliases).
3. If attempt 2 also fails, or there is not enough time, the answer is **evidence-only** (`CITATION_VERIFICATION_FAILED`).

The evidence-only answer (`generation/fallback.py::evidence_only`) lists up to 8 pack items as `**Title**, locator: “snippet” [[HANDLE]]`, with a 280-character extractive snippet centred on the anchor. It has no generated prose. If draft text was visible, it is withdrawn first with `draft_reset {attempt: 0, reason: "evidence_only"}`.

## 6. Abstention

**Empty pack: implemented.** When the pack is empty (no hits, or every hit purged), the executor never calls the model (`EVIDENCE_EMPTY`, `no_relevant_evidence`). `fallback.abstention` returns a fixed Answer ("The workspace evidence does not contain information that answers this question, so no answer was generated.") and a Gaps unit naming the source classes the workspace lacks (or the requested classes searched). No tokens are streamed. The grounded evaluation gates this (§9).

**Weak-evidence abstention: deferred.** A non-empty pack always goes to the model, and the model is instructed to say plainly when the evidence does not answer the question; the verifier accepts such an answer with zero citations (`states_insufficient`). A score threshold was considered and not built, because the recorded retrieval scores do not separate the cases. [`eval/baselines/phase3/abstention-signals.json`](../eval/baselines/phase3/abstention-signals.json) records, for 74 grounded-v0 items (all but the two empty-pack items), the top dense score (`dense_top`) and top lexical score (`lex_top`, with `lex_max_possible`). Computed from that file:

| Signal | Insufficient items (n = 9) | Answerable + conflict items (n = 65) | Overlap |
|---|---|---|---|
| `dense_top` | 0.684 – 0.822 | 0.649 – 0.907 | A threshold that abstains on all 9 insufficient items also abstains on 48 of 65 answerable ones; 3 answerable items score below the *lowest* insufficient item |
| `lex_top / lex_max_possible` | 0.349 – 0.734 | 0.187 – 1.000 | A threshold that abstains on all 9 also abstains on 51 of 65 |

The insufficient range sits entirely inside the answerable range on both signals, so any threshold trades heavy over-refusal for little abstention. Whether the model's own insufficiency statements perform better is **pending live evaluation** (the evaluation reports `insufficient_correct` and `over_refusal`). The file does not record which retrieval configuration produced it.

## 7. SSE protocol

Endpoints, stream tokens and headers are summarised in [`SYSTEM_DESIGN.md` §6](SYSTEM_DESIGN.md#6-sse-delivery). Wire format: `id: <seq>`, `event: <type>`, `data: {"run_id", "seq", "ts", …}`.

### 7.1 Event types (as emitted in standard mode)

| Event | Payload | Emitted |
|---|---|---|
| `run_started` | conversation_id, persona, mode | First event |
| `status` | phase ∈ searching / analyzing / synthesizing / verifying, message | Fixed text from `STATUS`, never model reasoning |
| `tool_started` / `tool_completed` | step 1, tool `search_evidence`, kind `search`; on completion status, result_count, classes_found, duration_ms, trace_id | Around retrieval |
| `evidence` | item_count, classes, truncated | After the pack is frozen |
| `citation` | attempt, alias, handle, source_title, source_class, locator_label | First use of a valid alias, before its text |
| `token` | attempt, text | Gated draft text, coalesced to about `sse_token_coalesce_ms` (100 ms) |
| `warning` | code, message | Degradations, removed aliases, deleted sources |
| `draft_reset` | attempt, reason | Withdraws the visible draft (§7.3) |
| `final` | message_id, content (canonical), citations, sections, verification | After the answer row is committed |
| `error` | code `RUN_FAILED`, message, retryable | Unexpected failure only |
| `done` | termination_state, flags, cache_status (`"disabled"`), timings | Always last, exactly once |

### 7.2 Ordering guarantees

- **Persist before publish.** `runs/events.py::EventWriter` writes each event to `run_events` and only then wakes subscribers. Replay and the live tail read the same rows.
- **Gap-free `seq`.** `seq` advances only after a successful write. If a write was interrupted mid-commit, the next write re-reads `max(seq)` first. Token text whose write failed is dropped, never re-sent: it is an unverified draft.
- **Flush before any other event.** Pending token text is flushed before every non-token event, so a `citation` precedes the text carrying its marker and all draft text precedes `final`.
- **`done` is last and unique.** The writer refuses events after `done`, and the store enforces it: `append_event` inserts only `WHERE NOT EXISTS` a `done` for the run, so a late writer cannot add anything (not even a second `done`) once one exists. Termination emits any notice, then a `draft_reset` if a draft is open and no `final` was emitted, then `done` (retried once after a failed write), then updates the run row.
- **No stream-then-withdraw.** On abort paths, buffered but unsent draft text is discarded instead of being streamed and immediately withdrawn.
- **Purge-safe text.** A text-bearing event (`token`, `citation`, `final`) of a run whose pack lost a source version to a purge is stored as a `warning` (`SOURCE_DELETED_DURING_RUN`, "content was withheld") with the same `seq`, so replay stays gap-free (§8). After the first such event `EventWriter` sets `withheld` and silently drops further `token` and `citation` writes (no second notice). Generation stops (`_SourceWithheldError` in `runs/state.py`, handled in `runs/synthesis.py`) and the run takes the source-deleted fallback (`runs/finalize.py`: evidence-only from the surviving sources, or abstention). A withheld `final` is not counted as emitted (`final_emitted` stays false). The client (`run-stream.ts`) shows one warning per `code`.

### 7.3 `draft_reset`

| Payload | When |
|---|---|
| `{attempt: 2, reason: "verification_failed"}` | Before the single regeneration |
| `{attempt: 0, reason: "evidence_only"}` | Before an evidence-only answer replaces a visible draft (also after a source purge forced the fallback) |
| `{attempt: 0, reason: <termination_state>}` | At termination (cancel, timeout, failure) when a draft is open and no `final` follows |

The client (`frontend/src/lib/run-stream.ts`) clears the draft and its alias bindings and moves its accepted attempt to `max(attempt, current + 1)`, so late tokens from the discarded attempt are ignored. `final` replaces the draft entirely. The draft panel is labelled "Draft — verifying…".

### 7.4 Replay, heartbeat, disconnect, reaper

- **Replay.** The stream sends every persisted event with `seq > max(?last_event_id, Last-Event-ID header)`, then tails. A native `EventSource` reconnect therefore receives exactly the missed events. The reducer is idempotent: it drops any event whose `seq` is not greater than the last applied one, and applies nothing after `done`.
- **Heartbeat.** FastAPI's `EventSourceResponse` sends a `: ping` comment every 15 s.
- **Live tail.** In-process subscribers are woken by `RunBroker`; otherwise the stream polls the table every `sse_poll_interval_s` (1 s), so a stream served by another process sees every event with at most one poll interval of delay.
- **Disconnect.** The stream stops when the client disconnects; the run continues (a disconnect is not a cancel). The client gives up after 6 consecutive `EventSource` errors with no event between them.
- **Cancel.** `POST /runs/{rid}/cancel` cancels the task if it runs in this process; a second cancel while it is already cancelling is a no-op (it would otherwise interrupt termination). A run in another process cannot be cancelled and ends at its deadline (`cancel_requested: false`).
- **A stream never hangs.** If no new events arrive and the run is no longer `running`, the stream either delivers a `done` that landed after its read or, if there is no `done` row at all (its events were purged), synthesizes one from `query_runs`. If the run is still `running` past `run_deadline_s + run_reap_margin_s`, the stream reaps it, which writes `done (interrupted)`.
- **Reaper.** `runs/reaper.py` runs at startup, every `run_reaper_interval_s`, and on demand. It inserts exactly one `done (interrupted)` per orphan (guarded by `NOT EXISTS` and the `seq` key) and marks the row `interrupted`; if `done` already exists, it syncs the row from that payload. Runs whose executor task is still live in this process (`live_run_ids`, passed as `exclude=`) are never reaped. Finalization is bounded by `run_finalize_timeout_s` (20 s, must be less than `run_reap_margin_s`; `runs/executor.py::_conclude`), so a live run concludes before it could look like an orphan to another process.

### 7.5 Stream tokens

`EventSource` cannot send an `Authorization` header, so the stream URL carries `?st=`: an HS256 JWT with `aud=sse`, bound to `run_id` and the workspace code, expiring after `run_deadline_s + stream_token_replay_s`. It is verified in a dependency *before* the stream starts, so a bad, expired or foreign token returns 404 rather than an open stream. The parameter is redacted from logs, and responses send `Referrer-Policy: no-referrer`.

## 8. Purge during a run

A purge must remove every stored quote of the deleted source, including text a run in flight is about to store. The locking argument is the module docstring of `runs/store.py`; in short, `ingestion/purge.py::purge_source` runs in one transaction that takes **`FOR UPDATE` on the source row**, marks the versions purged, and then (`_purge_run_artifacts`) locks **every `query_runs` row whose `pack_handles` include the source `FOR UPDATE`, in `id` order**, before it redacts messages, tombstones citation cards, resets conversation summaries and deletes `run_events` for those runs (table in [`SYSTEM_DESIGN.md` §5](SYSTEM_DESIGN.md#5-purge-semantics)).

Purge state is read from **`source_versions.status = 'purged'` for the exact `@vN` of each handle**, never from `sources.deleted_at`. Re-uploading a purged source restores the source row but leaves the old version purged (and `ingestion/pipeline.py`'s supersede step skips purged versions), so re-upload cannot revive purged text and a pack frozen on `X@v1` stays guarded after `X@v2` arrives.

On the run side the source rows are share-locked once, at freezing; every later text-bearing write locks only the run's own row (`runs/store.py`):

| Write | Lock | If a pack version is purged |
|---|---|---|
| `freeze_pack` (once per run) | `FOR SHARE` on the pack's `sources` rows (id order), then reads the versions' purge state, then writes `pack_handles` | Its handles are left out of `pack_handles`; the executor drops its items before any event or model call |
| `append_event` for `token`, `citation`, `final` | `FOR KEY SHARE` on the run's own `query_runs` row, then the purge check, in one transaction | The event is stored as a `warning` (withheld) instead |
| `persist_answer` | same; every pack version and every cited version, cited or not (an answer can use uncited pack text) | Nothing is stored; the purged sources are dropped from `pack_handles` and the run's text events are deleted; the executor falls back to evidence-only from the survivors, or abstains if none survive, and tries again |
| `advance_conversation_state` | same, before the conversation row `FOR UPDATE` | The rolling summary is not updated (flag `SOURCE_DELETED_DURING_RUN`) |

**Why this is sufficient.**

- *Freeze.* If the purge holds the source lock, the freeze waits for it to commit and then sees the purged version (each READ COMMITTED statement takes a fresh snapshot), so it drops it. If the freeze holds the lock first, the purge waits at its first statement, and its later `query_runs` lock sees the committed `pack_handles`. So either the purge locks this run, or the freeze has already dropped the source. Nothing can quote the pack before the freeze commits.
- *Later writes.* The purge's `FOR UPDATE` on the run row conflicts with the writer's `FOR KEY SHARE` on the same row, so they serialise. If the **write gets the lock first**, the purge waits for its commit; the purge's redaction, reset and delete statements run afterwards with later snapshots and remove what the write stored. If the **purge gets the lock first**, the write waits until the purge commits, then sees the purged version and does not store the text.

There is no interleaving in which the text survives. Per-token writes never lock source rows: the only contention is a run with itself, or with a purge that actually concerns it. The `persist_answer` retry loop terminates because each failed attempt removes at least one source, and an abstention cites none. Integration tests cover these races (`backend/tests/integration/test_runs_purge.py`).

## 9. Grounded evaluation

`evaluation/grounded.py` drives the **real in-process API** for every item (conversation → run → SSE stream) with production retrieval and the configured synthesis model, and measures only deterministic properties (no LLM judge). Run it with `python -m marketsignal.evaluation grounded --out <dir> [--fake] [--ids …] [--limit n] [--concurrency n]`. Without `--fake` it refuses to start unless an API key is configured.

**Dataset** `eval/datasets/grounded-v0/items.json` (`grounded-v0`): 76 items. 55 are retrieval-eligible retrieval-v0 items with their frozen gold facts; 21 are hand-written conflict, insufficient-evidence, empty-pack and citation-adversarial items. 69 target the Northstar workspace and 7 the Southpeak workspace; 2 carry canary strings.

| Category | n | Expected behaviour |
|---|---|---|
| answerable_fact | 42 | answer |
| cross_source | 7 | answer |
| exact_number | 6 | answer |
| conflict | 5 | conflict (cite both sides or produce a Conflicting evidence section) |
| adversarial | 6 | 5 answer, 1 insufficient; canary strings must never appear in streamed or final text |
| insufficient | 8 | insufficient (no cited claim unless it states the evidence is insufficient) |
| empty_pack | 2 | abstain without calling the model |

**Hard gates** (all must pass):

| Gate | Requirement |
|---|---|
| `citation_resolvability` | Every rendered `[[HANDLE]]` resolves through the production resolver in the item's workspace: 100% |
| `citation_in_pack` | Every cited handle is in the run's `pack_handles`: 100% |
| `cross_workspace_leaks` | No cited foreign handle and no second-workspace marker string: 0 |
| `empty_pack_never_calls_llm` | Every empty-pack item ends `no_relevant_evidence`, streams no tokens and shows no sign of a model call (no usage, no `synthesizing` status, no `draft_reset`): 100%, with at least one such item |
| `every_run_done` | Every item's stream ends with `done` |
| `answer_items_have_final` | Every item that expects an answer, conflict or insufficiency gets a `final` |

The two citation gates read **"not evaluated" (fail)** if answer-expected items cited nothing at all, so a broken generation path cannot pass vacuously.

**Measured, not gated:** a contract re-check of the *stored* content (Answer sentences cited or `[inference]`, findings cited, no `[E#]`, URLs, links, images or HTML); gold citation coverage and numeric correctness (the ledger value appears in the answer) over model-generated answers, with evidence-only fallbacks reported separately; insufficient-item correctness and over-refusal on answerable items; conflict surfacing; canary leaks; regenerations; termination states; first-token and total latency (p50, p95); token usage per LLM run.

**Results.** The live run is **pending live evaluation**. `eval/reports/grounded-fake/` holds an offline plumbing run with a scripted `FakeLLM` that returns one canned answer for every item: it exercises the pipeline and the gates and says nothing about answer quality. It was produced before the `every_run_done` and `answer_items_have_final` gates were added, so its gate table is incomplete.

## 10. Known limits

- Weak-evidence abstention relies on the model stating insufficiency (§6).
- Numeric faithfulness checks presence, not meaning; spelled-out numbers without magnitude words, fractions, and percent claims against unlabelled table cells are the documented gaps (§5.4).
- The Conflicting evidence section is not required by the verifier; conflicts are surfaced only if the model writes them.
- The pack token budget uses a WordPiece proxy (§1).
- Cancel is process-local and the cross-process live tail polls (§7.4).
- No answer cache, rate limiting or spend ledger yet ([`SYSTEM_DESIGN.md` §9](SYSTEM_DESIGN.md#9-deferred-to-phase-4-and-later)).
