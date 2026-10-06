# ADR-0008: SSE run protocol over WebSockets

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** Planned — Phase 3 (runs, `run_events`, SSE, chat UI draft/final); progress events extended in Phase 4; deployed-browser check in Phase 9 (this ADR is updated with measurements when the component is built)
- **Related:** plan §3, §21, §25, §32.1; ADR-0004 (aliases and hold-back gate), ADR-0007 (agent), ADR-0009 (workspace isolation), ADR-0014 (deployment and browser auth); approved deviation D7

## Context

A research run takes seconds to tens of seconds (targets: end-to-end p50 under 15 s standard, about 25 s research; 60 s run deadline). Users need progress and an early draft, but the answer is only trustworthy after deterministic citation verification. The stream must therefore separate an *unverified draft* from a *verified final*.

Constraints:
- Traffic is one-way, server to client. Client actions (start, cancel) are discrete.
- The frontend (Vercel) and API (Render) are different sites. Both suffixes are on the Public Suffix List, so cookies would be third-party and Safari ITP blocks them. The browser `EventSource` API cannot set an `Authorization` header.
- Networks drop. A reconnect must not lose events, and a disconnect must not cancel paid LLM work.
- API replicas must be stateless (scaling path, §34).

## Decision

**Endpoints.** All are workspace-scoped (ADR-0009).
- `POST /api/workspaces/{ws}/conversations/{cid}/runs` → `202 {run_id, stream_url}` (target under 150 ms).
- `GET /api/workspaces/{ws}/runs/{rid}/events?st=<stream token>[&last_event_id=n]`
- `POST /api/workspaces/{ws}/runs/{rid}/cancel`

**Stream token.** HS256, `aud=sse`, `run_id`, `ws`, `sub`, `exp` = run max duration + 15 min replay window. It travels in the URL because `EventSource` cannot send headers and no cookies are used. It is redacted from access logs (`st` is in the structlog redaction list) and responses send `Referrer-Policy: no-referrer`. A stream whose `ws` does not match the route returns 404.

**Wire format.** Every event: `id: <seq>`, `event: <type>`, `data: {"run_id", "seq", "ts", …}`. A `: ping` heartbeat every 15 s. Implemented with FastAPI's native `EventSourceResponse`; `X-Accel-Buffering: no` is set and the frontend connects to the API origin directly, because dev proxies buffer SSE.

**Event family.** `run_started`, `status` (deterministic phase text, never model reasoning), `tool_started` / `tool_completed` (with `kind` ∈ search/keyword/resolve/catalog/analytics/hypothesis and sanitized arguments), `evidence`, `draft_reset`, `token` (through the alias hold-back gate, coalesced to about 100 ms), `citation` (once per alias when validated), `warning`, `final`, `error`, `done`.

**Draft/final semantics.**
- `token` events form a draft labelled "Draft — verifying…"; citation chips stay pending until `citation` validates them.
- `draft_reset {attempt, reason}` tells the client to clear the draft before a regeneration or an evidence-only fallback.
- `final` carries the canonical content (handles, not aliases), citation cards, parsed sections and the verification report. **It is the source of truth and replaces the draft.**
- `done {termination_state, flags, cache_status, timings}` is **always the last event**.
- The alias hold-back gate holds text from a `[` only while it can still become `[E\d{1,2}]`, so at most 4 characters are held.

**Postgres replay log.** Every event is appended to `run_events(run_id, workspace_id, seq, type, payload)` with PK `(run_id, seq)`, under RLS. Live tail uses in-process fan-out plus LISTEN/NOTIFY for subscribers on other processes. Replay sends `seq > Last-Event-ID`. A startup reaper marks orphaned `running` runs as interrupted and emits `done`. Retention: 30 days, nightly job.

**Run independence.** A run executes independently of its subscribers; a disconnect is not a cancel. A partial answer is persisted as `incomplete`, without unverified citations. Cancel is an explicit POST and also revokes the run's MCP capability token (ADR-0006).

## Approved spec deviation

- **D7. Spec position:** SSE events `search_started/…` (per-operation event names).
- **Approved change:** use `tool_started` / `tool_completed` with a `kind` field, add `draft_reset`, and send `final` before `done`.
- **Reason:** one event family covers every tool, and the verified `final` answer supersedes the streamed draft. No additional approval requirement was attached to D7.
- Approved 2026-10-05.

## Alternatives considered

- **WebSockets.** Bidirectional connection state that nothing here needs; client actions are ordinary POSTs. WebSockets have no built-in resume, so Last-Event-ID replay would have to be rebuilt by hand, and they fit less naturally through HTTP proxies and HTTP/2.
- **Buffer until `final`.** Safest (no unverified text is ever shown) but the user sees 8–15 s of silence instead of a first token in under 2 s (targets, not measurements).
- **Cookie-authenticated SSE.** Blocked as third-party across `vercel.app` / `onrender.com`. A same-origin Vercel rewrite with a first-party cookie, or custom `app.`/`api.` subdomains, would work but add infrastructure; documented as alternatives in ADR-0014.
- **Ephemeral in-memory streams (no persisted log).** No replay after reconnect, no multi-replica subscribers, and no record of what the user actually saw.
- **sse-starlette.** Viable, but FastAPI's built-in SSE response now covers the need without another dependency.

## Tradeoffs accepted

- The user can briefly see a draft sentence that verification later removes. The draft is labelled unverified, chips stay pending, and `final` replaces it.
- A bearer credential in a URL. Mitigated by audience, run and workspace binding, a short expiry, log redaction and `no-referrer`.
- Every event is a Postgres write. Acceptable at demo scale; `token` coalescing to about 100 ms bounds the write rate.
- Long-lived connections need idle timeouts above the heartbeat interval on any proxy (the AWS reference design sets ALB idle timeout ≥ 300 s).

## Consequences

**Positive**
- Native `EventSource` reconnect with Last-Event-ID; replay is a simple indexed range read.
- Stateless replicas: any process can serve a stream from the log plus NOTIFY.
- `run_events` doubles as an audit trail of what the user saw (§25).
- Only verified, canonical-handle answers are persisted as final.

**Negative**
- Two representations of the answer (draft tokens, final) that the client reducer must reconcile.
- An extra table with retention management.

**Follow-ups**
- Record measured `run_started` latency, first-token latency and end-to-end p50/p95 per mode from `query_runs.timings` and the load test.

**Verification**
- SSE event-order contract test (`done` last, `final` before `done`, `draft_reset` before regenerated tokens) and SSE JSON-schema contract tests.
- Alias hold-back gate unit test with randomized delta splits.
- Integration: SSE resume with `last_event_id` returns exactly the missed events.
- Frontend: vitest for the SSE reducer and chip parsing; Playwright smoke (ask → stream → open citation) against a FakeLLM backend.
- Phase 9 exit check: ask → stream → final → reconnect mid-run, manually in Safari and Chrome incognito against the deployed URL.

## Implementation notes (Phase 3, 2026-10-05)

Built in `api/routers/runs.py`, `runs/events.py`, `runs/executor.py`, `runs/broker.py`, `runs/reaper.py`, `runs/tokens.py`, `runs/store.py`, migration 0004 and `frontend/src/lib/run-stream.ts`. Design detail: [`docs/GROUNDED_ANSWERING.md`](../GROUNDED_ANSWERING.md) §7.

- **As decided:** the three endpoints; HS256 stream tokens (`aud=sse`, run- and workspace-bound, lifetime run deadline + 900 s replay window, verified before the stream opens, any mismatch → 404); `id/event/data` wire format; FastAPI's native `EventSourceResponse` with its **15 s `: ping`**; `X-Accel-Buffering: no`, `Cache-Control: no-cache` and `Referrer-Policy: no-referrer`; replay of `seq > Last-Event-ID` (header or `?last_event_id`, the larger wins); `done` always last and exactly once; disconnect is not a cancel.
- **Persist-then-notify.** Every event is written to `run_events` before subscribers are woken, so replay and live tail are one code path. `seq` is gap-free: it advances only after a committed write, and an interrupted write forces a `max(seq)` re-read. Token text is coalesced (~100 ms) and flushed before any other event.
- **Deviation: no LISTEN/NOTIFY.** Live tail uses an in-process broker (`RunBroker`) plus a **DB-polling fallback** every `sse_poll_interval_s` (1 s) for subscribers in other processes. LISTEN/NOTIFY remains the documented next step.
- **Deviation: cancel is process-local.** `POST …/cancel` cancels the task only in the process running it; elsewhere it returns `cancel_requested: false` and the run ends at its deadline. Cross-process cancel needs a shared signal. There is no MCP capability token to revoke in standard mode.
- **Deviation: `interrupted` termination state.** The reaper (startup, periodic, and on demand from an overdue stream) closes a run still `running` past deadline + reap margin with exactly one `done {termination_state: "interrupted"}` (flag `RUN_INTERRUPTED`) and status `interrupted`. Runs whose executor task is still live in the reaping process (`live_run_ids`, `exclude=`) are skipped, and finalization is bounded by `run_finalize_timeout_s` so a live run concludes before the age threshold. This extends the plan §28 enum; the migration's CHECK constraint includes it.
- **`done` is last in storage too.** `run_events` inserts are refused once a `done` exists (`append_event` inserts `WHERE NOT EXISTS`), so no writer can add an event after it.
- **Withheld text.** When a purge removes a pack source mid-run, the first text-bearing event (`token`, `citation`, `final`) is stored as a `SOURCE_DELETED_DURING_RUN` `warning` with its `seq`; `EventWriter` then drops further `token`/`citation` writes, generation stops, and the run ends with the evidence-only fallback. A withheld `final` does not count as emitted. The client shows one warning per `code`.
- **Never-hanging streams.** A run that is not `running` and has no `done` row (its events were purged) gets a synthesized `done` built from `query_runs`.
- **`draft_reset` reasons in use:** `verification_failed` (attempt 2), `evidence_only` (attempt 0), or the termination state (attempt 0) when a visible draft is abandoned. Unsent draft text is discarded on abort paths rather than streamed and withdrawn.
- **Deviation: no `incomplete` messages.** A run without `final` stores no assistant message; the `incomplete` status exists in the schema but is not written.
- **Retention decision (from ADR-0016):** `run_events` are kept 30 days; the deletion job is Phase 8. UPDATE is revoked from `ms_app`.
- **Not yet verified:** the manual Safari/Chrome reconnect check against the deployed URL (Phase 9).
