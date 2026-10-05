# ADR-0009: Workspace isolation in depth

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** **Phase 0 implemented** (roles, RLS scaffolding, readiness guard, scope listener); applied to each tenant table as it is added from Phase 1 onward; hardened in Phase 8
- **Related:** plan §6, §8 (RLS × GIN caveat), §22, §23, §24, §32.2, §34; ADR-0001 (Postgres), ADR-0006 (MCP boundary), ADR-0008 (SSE), ADR-0010 (job queue); approved deviation D8

## Context

Each workspace holds one client engagement's documents. A leak across workspaces is the worst failure the product can have, and an LLM in the loop raises the stakes: retrieved text from another tenant would be summarized and cited with apparent authority.

Application-only scoping is one missing `WHERE workspace_id = …` away from a leak. Postgres row-level security (RLS) adds a database-enforced layer, but it is easy to make it look enforced while it is not: superusers, table owners without `FORCE` and roles with `BYPASSRLS` all skip policies. RLS also needs the workspace set on the connection *before* the first read in a transaction, which requires the workspace to be known from the request itself.

## Decision

Defence in depth, nine layers. Each one fails closed.

1. **Route.** Every tenant route is `/api/workspaces/{ws}/…`. The principal must be a member (`workspace_members`; single demo principal for now). A contract test asserts every non-health, non-auth route contains `{ws}`.
2. **Scoped repositories.** Every data-access function requires a `WorkspaceScope`, which only the authorizing dependency or the worker job prologue can construct. No unscoped helpers exist; a test enumerates repositories to prove it.
3. **RLS under a non-owner, non-superuser role.**
   - `ms_owner` owns the schema and runs migrations. `ms_app` is `LOGIN NOSUPERUSER NOBYPASSRLS`, owns nothing, has DML grants only; both API and worker connect as it. `ms_eval` serves only the eval runner.
   - Every tenant table has **ENABLE + FORCE RLS** with `USING / WITH CHECK (workspace_id = app.current_workspace())`.
   - `app.current_workspace()` is a STABLE function returning `NULLIF(current_setting('app.workspace_id', true), '')::uuid` and raising `WORKSPACE_SCOPE_NOT_SET` when unset, so a fresh connection and a pooled connection with a cleared setting fail identically.
   - An SQLAlchemy `after_begin` listener runs `SELECT set_config('app.workspace_id', :ws, true)` (transaction-local) from the `WorkspaceScope` contextvar and raises if no scope exists. Every autobegun or per-stage transaction is re-scoped. `SET` with a bind parameter is not used (syntax error).
   - Startup and `/readyz` fail if the current role has `rolsuper OR rolbypassrls`.
4. **Composite foreign keys.** Each tenant table has `UNIQUE (workspace_id, id)` and references parents by `(workspace_id, x_id) → parent(workspace_id, id)`, so the database itself proves a child cannot belong to another tenant's parent.
5. **Tools** take the workspace only from capability-token claims; no tool schema has a workspace field (ADR-0006).
6. **Handles** embed the workspace code, which must match the scope. A foreign handle returns `NOT_FOUND`, never revealing existence.
7. **Cache keys** include `workspace_id`; run event streams are bound to `ws` (404 on mismatch).
8. **Deterministic CI tests as `ms_app`** (below).
9. **Behavioral evaluation** with a decoy workspace (fictional *Southpeak Outdoor*, 6 docs with canary facts) that must never appear in Northstar answers, and the reverse. In the public demo, visitor uploads go to a Sandbox workspace that Northstar answers must never cite.

Non-tenant tables are explicit: `workspaces` and `workspace_members` are read only via a membership-checked repository; `spend_ledger` and Procrastinate's tables carry no tenant data and have no RLS (ADR-0010 covers how jobs re-establish scope).

**RLS × GIN caveat (accepted at demo scale).** `@@` (`ts_match_vq`) is not `LEAKPROOF`, so under FORCE RLS the planner will not use the GIN index on `tsv` ahead of the security-barrier policy; for `ms_app`, lexical search filters the workspace's rows sequentially. At about 3–5k children per workspace this costs milliseconds (plan estimate). It is documented, backed by EXPLAIN evidence and guarded by an EXPLAIN-based regression test. The HNSW `ORDER BY` is not a filter condition and is unaffected. **Scale remedy:** move lexical candidate SQL to a narrow SELECT-only `ms_retrieval` role that bypasses RLS and is used only by the scope-enforcing lexical repository with an explicit `workspace_id` predicate, or partition by workspace.

## Approved spec deviation

- **D8. Spec position:** `GET /api/evidence/{handle}` and unscoped conversation routes.
- **Approved change:** every tenant route lives under `/api/workspaces/{ws}/…` (for example `GET /api/workspaces/{ws}/evidence/{handle}?run_id=`).
- **Reason:** workspace authority must come from the route and the principal. Without it, RLS scope cannot be set before the first read. No additional approval requirement was attached to D8.
- Approved 2026-10-05.

## Alternatives considered

- **Application-only scoping.** Simplest, no RLS overhead, but one bug away from a leak and nothing in the database proves isolation.
- **Schema-per-tenant or database-per-tenant.** Stronger isolation, but migrations multiply per tenant and pooled connections must switch schemas or databases. Database-per-tenant remains the option for very large tenants (§34).
- **Deriving the workspace from the handle or conversation ID** (the spec's unscoped routes). Requires an unscoped read to find the workspace before scope can be set, which is exactly the read RLS is meant to block.
- **Marking `ts_match_vq` LEAKPROOF** to restore GIN use. Needs superuser; unavailable on managed Postgres.
- **Connecting as the schema owner.** Owners bypass RLS unless FORCE is set, and superusers bypass it always; this gives false confidence. Prevented by the role topology and the readiness guard.

## Tradeoffs accepted

- RLS adds per-query overhead and disables GIN for lexical search under `ms_app`; accepted at demo scale with a documented remedy.
- Role plumbing (three roles, grants, a role init script in compose and CI, the `after_begin` hook) adds setup complexity.
- Composite keys make every tenant table and foreign key wider.
- Isolation depends on the hosting provider allowing `CREATE ROLE` with a non-superuser, non-BYPASSRLS credential (Phase 0 spike; Railway fallback).

## Consequences

**Positive**
- A missing scope fails closed with `WORKSPACE_SCOPE_NOT_SET` instead of returning all rows.
- Cross-tenant inserts are rejected by `WITH CHECK` and composite FKs even if application code is wrong.
- Isolation is demonstrable in an interview with deterministic tests and the decoy workspace.

**Negative**
- Lexical retrieval cost grows linearly with workspace size until the scale remedy is applied.
- Background jobs and eval must construct scope explicitly; there is no "admin read".

**Follow-ups**
- Record the measured lexical-lane latency under `ms_app` and the EXPLAIN plan once the corpus is seeded.
- Apply the `ms_retrieval` role or partitioning when the lexical lane stops being a few-millisecond cost.

**Verification**
- CI integration tests connected as `ms_app`: with scope A, workspace B's rows count 0; a cross-workspace INSERT fails WITH CHECK; with no scope, the query errors; the worker cannot read another workspace's children; dense and lexical lanes never return B's ids.
- Route-scoping contract test and repository enumeration test.
- Readiness test: `/readyz` fails when connected as a superuser or BYPASSRLS role.
- EXPLAIN-based regression test documenting the RLS × GIN plan.
- Behavioral eval: zero Southpeak canary facts in Northstar answers and the reverse, checked deterministically from traces and answers.

## Implementation status (Phase 0, 2026-10-05)

| Item | Where | Verified by |
|---|---|---|
| `ms_owner` / `ms_app` roles (both `NOSUPERUSER NOBYPASSRLS`; DB owned by `ms_owner`) | `backend/db/init/01_roles.sh` (compose initdb + CI) | catalog check: `rolsuper=f, rolbypassrls=f` |
| `app.current_workspace()` raises `WORKSPACE_SCOPE_NOT_SET` on a missing or empty GUC | migration `0001` | `test_unscoped_query_fails_closed_on_fresh_and_reused_connections` |
| ENABLE + FORCE RLS with the `USING` / `WITH CHECK` policy | `workspace_corpus_state` (first tenant table) | `test_scope_a_sees_only_workspace_a`, `test_cross_workspace_write_is_rejected_by_with_check` |
| Transaction-local scope via `set_config(..., true)` in an `after_begin` listener; no scope means fail closed | `marketsignal.db.scope` | `test_orm_session_sets_scope_per_transaction` + unit tests |
| Startup and `/readyz` refuse superuser/BYPASSRLS connections | `marketsignal.api.app`, `marketsignal.health` | `test_startup_refuses_superuser_connection`; manual start with the superuser URL exits with "Application startup failed" |

**Non-vacuity check.** The same isolation suite run deliberately as the bootstrap **superuser** fails 5/5. This confirms that the tests detect an RLS bypass and do not pass merely because the data happens to be separated.


## Implementation status (Phase 1, migration 0002)

- All nine evidence-model tables (`sources`, `source_versions`, `source_blobs`, `parent_chunks`, `child_chunks`, `chunk_embeddings`, `dataset_tables`, `dataset_rows`, `audit_events`) use ENABLE + FORCE RLS with the standard policy.
- Every cross-table reference is a composite `(workspace_id, x_id)` foreign key.
- **Tenant-scoped keys.** Tables keyed by another row's id (`source_blobs`, `chunk_embeddings`) include `workspace_id` in their primary key. A global key would let workspace B learn that one of A's ids exists, because B would get a *uniqueness* error instead of an FK error. The isolation test suite found this, and the keys were changed before the migration was committed.
- `audit_events` is append-only for `ms_app` (UPDATE and DELETE are revoked).
- Verified by `tests/integration/test_evidence_model_isolation.py`, which has 31 tests running as `ms_app`. Run as superuser, all 24 RLS and privilege tests fail, as they should. The 7 composite-FK and idempotency tests still pass, because foreign keys hold for every role.
