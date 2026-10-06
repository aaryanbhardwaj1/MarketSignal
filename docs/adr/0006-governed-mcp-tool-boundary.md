# ADR-0006: Governed MCP tool boundary

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** Built in Phase 4 (four of six data tools; see Implementation notes). **Phase 0 spike passed** (`docs/spikes/0001-mcp-sdk-v2.md`; executable record `backend/tests/spikes/test_mcp_v2_spike.py`): FastAPI mount, HS256 capability-token verification, claims via `get_access_token()`, `Context` hidden from the schema, structured outputs.
- **Related:** plan §2.1, §17, §18, §23, §24, §28; ADR-0002 (hybrid retrieval), ADR-0004 (evidence handles), ADR-0005 (cross-encoder reranker), ADR-0007 (agent state machine), ADR-0009 (workspace isolation); approved deviation D3 (and D9, tool allowlist)

## Context

In research mode an LLM chooses which data operations to run. Every such operation reads tenant data, so the place where the model reaches data is the security and quality boundary of the system. Four requirements shape it:

1. The model must never pick the workspace, a file path or SQL. Tenant authority has to come from the server, not from model-generated arguments.
2. Every call needs the same governance: authorization, strict input validation, timeouts, output caps, error normalization and an audit row.
3. Tool selection quality falls when tools overlap. A tool that lets the model skip fusion and reranking would also skip the retrieval quality work (ADR-0002, ADR-0005).
4. The demo runs on a small budget (one API service and one worker), and the MCP SDK major version (`mcp` 2.x, spec revision 2026-07-28) was only days old when the plan was written.

## Decision

**Placement.** The MCP server is its own module and ASGI app (`MCPServer("marketsignal")`, `mcp` SDK 2.3.x, exact pin), mounted inside the API service at `/mcp`. It accepts **loopback clients only** unless `MCP_PUBLIC=true` is set. The agent reaches it over loopback Streamable HTTP. A stdio entrypoint serves local MCP clients (Claude Desktop, Claude Code) and is described as *trusted local mode*, not as an authentication mechanism. The same image can run the server as a separate process by changing the command.

**Run-scoped capability token.** For each run the API mints an HS256 token with a dedicated `MCP_TOKEN_KEY` and a pinned algorithm. Claims: `aud=mcp`, `iss`, `iat`, `nbf`, `exp` = the run deadline, `jti=run_id`, `sub=principal`, `ws`, `wsc` (workspace code), `persona`, `tools=[…]`, `max_conf`. The verifier checks signature and claims with ±5 s clock skew, and confirms the run is still `running`, so cancelling or finishing a run revokes its token. The server builds `ToolContext` from the claims. **No tool schema has a workspace, user, path or SQL field.**

**Stateless tools.** Tools are pure request → response. The evidence pool and call budgets belong to the agent runtime (ADR-0007), not to the server. Any replica can therefore serve any call, which matches the stateless MCP spec revision. Optional defence in depth: an atomic `UPDATE query_runs SET tool_calls = tool_calls + 1 WHERE id = :run AND tool_calls < :max RETURNING …`.

**Governance pipeline (per call, in order).** Verify token → check tool against `claims.tools` → strict Pydantic input validation → run under `asyncio.wait_for` plus Postgres `SET LOCAL statement_timeout` → cap output (items and characters, flag `TRUNCATED`) → normalize errors to `VALIDATION_ERROR | POLICY_DENIED | NOT_FOUND | TIMEOUT | UNAVAILABLE | INTERNAL` → write a `tool_runs` audit row → return typed `structured_content`, with document-derived text marked untrusted. Authorization and cookie headers are redacted from all logs.

**Consolidated tool surface.** Each registry entry has an input model, output model, implementation, timeout, result caps and required capability. The registry is transport-agnostic.

| Group | Tools |
|---|---|
| Catalog | `list_sources`, `get_source_metadata` |
| Retrieval | `search_evidence` (full hybrid pipeline), `search_evidence_keyword` (exact, exhaustive counts), `get_evidence` (handle resolution) |
| Analytics | `query_structured_metrics` (typed op DSL over polars; no SQL surface) |
| Hypothesis | `analyze_hypothesis_evidence` (composite deterministic workflow) |
| Harness-local, not MCP | `finish_research` (ADR-0007) |

**Retrieval output contract (D1 anchors).** `EvidenceHit` (plan §18), returned by `search_evidence` and `search_evidence_keyword`, carries `anchor_child_id`, `anchor_char_start` and `anchor_char_end` (offsets into the parent text) alongside the handle, scores and `expansion_kind`. These fields travel in `structured_content` into the agent's evidence pool (ADR-0007), so the pack and stored citation cards keep the exact supporting span (ADR-0003). The model itself sees only the compact observation (ADR-0007).

Column and table names are validated against the inferred schema and never interpolated into SQL. Workspace and confidentiality limits (`max_conf`) are applied as SQL predicates from the claims.

**LLM-facing schema adapter.** `to_anthropic_tool()` strips keywords strict mode does not support (length and range limits, `maxItems`), converts `oneOf` to `anyOf`, drops `discriminator`, sets `additionalProperties: false`, uses required-but-nullable fields and sorts tools by name for prompt-cache stability. Server-side Pydantic validation stays the security boundary.

**Delivery.** Phase 4a uses an in-process transport over the same registry. Phase 4b switches to Streamable HTTP. A parity test confirms both behave the same, so an SDK regression cannot block the demo.

## Approved spec deviation

- **D3. Spec position:** expose `search_evidence_semantic`, `search_evidence_keyword` and `search_evidence_hybrid`.
- **Approved change:** the agent gets `search_evidence` (the full hybrid pipeline) and `search_evidence_keyword` (exact matching). Dense-only search exists internally for ablations and is not exposed to the model.
- **Reason:** overlapping tools make tool selection worse and would let the model skip fusion and reranking. No additional approval requirement was attached to D3.
- **D9 (related). Spec position:** personas influence "tool availability". **Approved change:** all personas share the same read-only tool set and differ in source-class priors, prompt policy and default mode. The allowlist mechanism (`claims.tools`) exists and is tested. Reason: restricting read-only tools lowers answer quality and gains no security.
- Approved 2026-10-05.

## Alternatives considered

- **Separate MCP container.** Stronger process isolation, but one more paid service and more deployment surface. The boundary we need is protocol and authorization, not process isolation; the same image can still be split out later.
- **Plain in-process function calls.** Cheapest, but there is no protocol boundary to point to, and governance becomes a convention rather than a single enforced path. Kept only as the test transport and as a degradation fallback.
- **Anthropic's hosted MCP connector.** Needs a public URL for the tool server and is not eligible for zero data retention (ZDR).
- **Workspace as a tool argument.** Simpler schemas, but it hands tenant selection to model output, which a prompt injection could influence.
- **Stateful server (per-run evidence pool in the server).** Breaks replica independence under the stateless spec revision and splits run state across two components.
- **FastMCP 1.x or custom JSON-RPC.** FastMCP 1.x receives security fixes only. Custom JSON-RPC would lose interoperability with standard MCP clients.

## Tradeoffs accepted

- A bug inside the API process could bypass the boundary, because the server shares the process. Mitigated by import-linter rules (`agent` cannot import `db` or `retrieval`; `tools` is the only path to services), a contract test that the agent's data access goes only through the MCP client, and the in-process test transport.
- The stdio mode has no authentication. It is documented as trusted local mode only.
- Strict-mode schemas cannot carry length or range limits, so those constraints live only in server-side validation, not in what the model sees.
- A brand-new SDK major increases API churn risk. Mitigated by an exact pin, a thin adapter and the in-process fallback (`TOOLS_TRANSPORT_FALLBACK`).

## Consequences

**Positive**
- One audited path from model to data. Every call leaves a `tool_runs` row with sanitized input, status, error category, duration and result handles.
- Tenant authority is cryptographically bound to the run and revoked when the run ends.
- Fewer, non-overlapping tools; the model cannot bypass fusion and reranking.

**Negative**
- Token minting, verification and the run-status check add work to every tool call.
- Two transports must be kept in parity.

**Follow-ups**
- Phase 0 spike: confirm the MCP v2 mount, JWT verification and a loopback client call on the pinned SDK.
- Record per-call governance overhead from `tool_runs.duration_ms` once built.

**Verification**
- Contract: agent data access goes only through the MCP client; import-linter contracts in CI; MCP tool-schema snapshot (a change also invalidates prompt caches).
- Keyed contract test: the full tool array with `strict: true` is accepted by `count_tokens`.
- Parity test: in-process vs Streamable HTTP transport.
- Contract: `EvidenceHit` anchor fields (`anchor_child_id`, `anchor_char_start`, `anchor_char_end`) survive tool output → evidence pool → pack → stored citation card (ADR-0003).
- Integration: standard and research runs with FakeLLM through real Streamable HTTP MCP and token auth.
- Unit: token rejected on wrong `aud`, expired `exp`, bad signature, non-`running` run; tool outside `claims.tools` returns `POLICY_DENIED`; non-loopback client rejected.
- Isolation: a handle from another workspace returns `NOT_FOUND` (ADR-0009).
- Degradation: `TOOLS_TRANSPORT_FALLBACK` has a named test (§28).

## Implementation notes (Phase 4, 2026-10-06)

Built in `backend/src/marketsignal/tools/` and `mcp/`; deep dive in [`docs/GOVERNED_TOOLS_AND_MCP.md`](../GOVERNED_TOOLS_AND_MCP.md).

- **Four of six data tools.** `search_evidence`, `search_evidence_keyword`, `get_evidence` and `list_sources` are implemented (`tools/impl/`). `get_source_metadata`, `query_structured_metrics` and `analyze_hypothesis_evidence` are **deferred**. `finish_research` is harness-local as decided. `search_evidence` always runs the production hybrid pipeline with the reranker off (`production_service`).
- **Source-class claim (addition).** The token may carry `classes` (the run's `source_classes`). Every tool intersects requested classes with it and never widens (`SOURCE_CLASS_FILTERED` when they do not intersect), and `get_evidence` treats other classes as `NOT_FOUND`. The pool is filtered again from the database class (`agent/pool.py::pool_to_candidates`).
- **Token lifetime.** `ttl_s = min(3600, agent_gather_budget_s + 60)` (95 s by default) rather than the run deadline. `verify` also requires `jti`, caps `exp − iat` at 3,600 s and rejects a future `iat`, all with ±5 s leeway against one clock.
- **Pipeline order as built** (`tools/governance.py`): verify → revocation (run `running`) → `claims.tools` policy → registry lookup (`NOT_FOUND`) → strict validation → execute (wall clock + `SET LOCAL statement_timeout`) → cap → **revocation recheck after the body** (output discarded, `UNAUTHENTICATED`, audited) → normalize → audit → return.
- **Fail-closed audit.** Every authenticated call writes a `tool_runs` row (migration 0005) with sanitized arguments (control characters dropped, strings ≤ 200). A failed audit write turns the call into `INTERNAL`. The insert is purge-safe (`FOR KEY SHARE` on the run row; `{"redacted": true}` if the run already saw a purged handle). Migration 0006 grants `UPDATE (args)` only, so purge can redact arguments in place.
- **Inputs.** Closed models (`extra="forbid"`), per-item string bounds, and control/surrogate characters rejected (`VALIDATION_ERROR`).
- **HTTP edge.** `CapabilityTokenVerifier` checks signature, claims and revocation before any MCP handling, `tools/list` included (DB failure → 401). `LoopbackOnly` also rejects (403) any request with `Forwarded`, `X-Forwarded-For` or `X-Real-IP` unless `mcp_public`. Deployment rule: `FORWARDED_ALLOW_IPS` must never be `*`. The `Host`/`Origin` allowlist is loopback-only unless public mode configures `mcp_allowed_hosts`. The session manager runs in its own lifespan task, and `/mcp` is a deferred mount that answers 503 until the governor exists.
- **Delivery.** In-process remains the default (`tools_transport=inprocess`). With `tools_transport=http`, `HttpToolTransport` is wrapped in `FallbackToolTransport`. A call whose server was never reached (`TRANSPORT_FAILURE`) is re-run in process and flagged `TOOLS_TRANSPORT_FALLBACK`; governor results are never retried. Parity is covered by `tests/integration/test_mcp_parity.py`.
- **Not built:** analytics handles, per-session/IP rate limits on `/mcp`, and the optional defence-in-depth run-call counter (`query_runs.tool_calls` is written once after the gather, not incremented per call).


## Phase 5 note (2026-10-06)

- **Analytics tools under the same boundary.** `describe_dataset`, `aggregate`, `group_compare` and `filter_rows` replace the planned `query_structured_metrics` (ADR-0020). They are registered in the same registry, granted through the same `tools` claim (`TOOL_NAMES`, now eight), run through the same `ToolGovernor` pipeline on both transports and write the same `tool_runs` audit rows. The workspace, confidentiality ceiling and class restriction still come only from the token. Each computing call also persists its result in `analytics_results` (migration 0007; forced RLS, no `UPDATE` for `ms_app`), purge-ordered by `FOR SHARE` on the source row and a version recheck.
- **Non-strict, but server-validated.** The live API limits the strict tool array as a whole (≤ 16 union-typed and ≤ 24 optional parameters), and the analytics schemas exceed both together. The four analytics tools are therefore offered with `strict: false` (`ToolEntry.strict`, kept over MCP HTTP by `mcp/client.py`). The security boundary is unchanged: the governor validates every call with strict Pydantic before execution, so a malformed argument is `VALIDATION_ERROR`. `test_strict_tool_array_stays_within_the_live_api_grammar_limits` guards the limits for the strict tools ([spike 0002](../spikes/0002-anthropic-live.md), Phase 5 addendum).
- **Purge guards.** A computing call's `tool_runs.result_handles` holds its source-version handle (and, for `filter_rows`, the listed row handles), so the existing purge redaction covers runs that analysed a purged source. `describe_dataset` records no handles.
