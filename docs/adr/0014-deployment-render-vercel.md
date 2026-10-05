# ADR-0014: Deployment on Render + Vercel, token-based browser auth, demo mode and spend ledger (AWS ECS/Fargate documented)

- **Status:** Accepted
- **Date:** 2026-10-05
- **Implementation:** Planned — Phase 9, with preconditions verified in the Phase 0 platform spike and the Phase 3 CPU spike (this ADR is updated with measurements when the component is built)
- **Related:** plan §0.2 (A5, A6), §2, §5, §21, §28, §31, §32, §32.1–§32.3, §33, §34, §35; ADR-0001 (single Postgres), ADR-0005 (local cross-encoder, hosted switch), ADR-0008 (SSE and stream token), ADR-0009 (workspace isolation), ADR-0011 (Redis optional), ADR-0012 (local embeddings); approved deviation D8 (all tenant routes under `/api/workspaces/{ws}/…`) as context

## Context

The system needs a public, low-maintenance hosted demo with these parts:
- a Next.js frontend;
- a FastAPI api with SSE and a mounted MCP endpoint;
- a Procrastinate worker;
- PostgreSQL 18 with pgvector (iterative scans need ≥ 0.8);
- Redis;
- local ONNX models (embedder and cross-encoder), which push the api and worker onto Render's 2 GB instance size (§32); peak RSS is measured in the Phase 3 CPU spike.

Constraints:
- **What the interview evaluates.** System design, retrieval, agent governance and evaluation. VPC, ALB and IAM work adds little signal per day spent.
- **Cost.** One person pays for the demo; costs are in §32.
- **Two origins.** Frontend and API live on different registrable domains. `vercel.app` and `onrender.com` are on the Public Suffix List, so any cookie would be third-party, and Safari ITP blocks third-party cookies.
- **Abuse.** A public URL that triggers LLM calls can run up unbounded spend.
- **Tenant isolation.** RLS relies on a non-superuser, non-BYPASSRLS application role (ADR-0009). The managed database must allow creating such roles.

## Decision

**Primary: Vercel (frontend) + Render.** Render hosts the api web service, the worker background service, Render Postgres with pgvector, and Render Key Value.
- One `render.yaml` blueprint, managed TLS, deploy on merge, and `alembic upgrade head` as a pre-deploy step.
- Estimated about $80/mo plus Vercel. Local models need the 2 GB instances for api and worker. About $45 is possible only with hosted embedding and reranking on 512 MB instances.
- **Phase 0 spike preconditions:** Render's pgvector is ≥ 0.8, and the default credential can `CREATE ROLE` without being superuser or BYPASSRLS. If either fails, the fallback is Railway with the `pgvector/pgvector` image.
- **Phase 3 CPU spike:** deploy the api image with models, run 10 queries, and record embed and rerank p50/p95 and peak RSS. These set the rerank timeout and pool. If rerank p95 exceeds about 1.5 s, production uses `RERANKER=voyage-rerank-2.5-lite`, and dev and CI keep local ONNX.
- **Operations:**
  - secrets in platform secret stores;
  - expand/contract migrations run before deploy;
  - `/readyz` health checks;
  - rollback by redeploying the previous image;
  - demo data seeded by a one-off job.

**Reference: AWS ECS/Fargate, documented and optional to build.**
- Components: ECS Express Mode or CDK, ARM Fargate tasks in public subnets with no NAT gateway, an ALB with idle timeout ≥ 300 s (plus 15 s SSE heartbeats), RDS PostgreSQL (verify the pgvector version), ElastiCache Serverless Valkey, S3 through the `BlobStore` adapter, Secrets Manager and ECR.
- Estimated about $75–85/mo without NAT and about $140+/mo with NAT. Copilot CLI is not used (end of support 2026-06-12).
- The same containers and environment config deploy there without code changes.

**Browser auth: tokens, no cookies (§32.1).**
- `POST /api/auth/demo` checks the passcode and returns a signed session token. The SPA keeps it in memory and in sessionStorage.
- REST calls send `Authorization: Bearer <token>` directly to the API origin. CORS uses an exact origin allowlist (never `*`) and no credentials mode.
- SSE uses the run-scoped stream token in the URL (HS256, `aud=sse`, redacted from logs, `Referrer-Policy: no-referrer`; ADR-0008).
- No cookies means CSRF does not apply. An Origin check on non-GET routes is kept as defence in depth.

**Demo mode (§32.2).**
- The session token carries a random `session_id`. Fixed-window rate limits in Redis apply per session and per IP. If Redis is down, an in-process limiter applies tighter, per-instance limits.
- Seeded workspaces are `demo_read_only`, so upload, delete and reindex return `POLICY_DENIED`.
- Visitor uploads go to a **Sandbox** workspace with per-session quotas, reset nightly. Northstar answers never cite Sandbox content, which also demonstrates isolation.
- `/docs` and `/openapi.json` are disabled or gated, `/metrics` requires a token, and `/mcp` accepts loopback only.

**Spend control (§32.3).**
- A Postgres `spend_ledger(month, cap_usd, spent_usd, reserved_usd)` sits outside tenant data. Before each LLM call, an atomic conditional `UPDATE … SET reserved = reserved + :worst_case WHERE spent + reserved + :worst_case <= cap RETURNING` reserves the worst-case cost. The reservation is reconciled against `usage` after the call.
- If no reservation is possible, the run goes evidence-only with `BUDGET_EXHAUSTED`.
- **Backstop:** a dedicated Anthropic Console workspace with a monthly spend limit for the deployed key.

## Alternatives considered

- **AWS ECS/Fargate as primary.** Production-grade and familiar to enterprise reviewers. It costs days of VPC, ALB, IAM and IaC work with little evaluation signal, and has NAT cost traps. Kept as the documented reference instead.
- **Railway.** A comparable PaaS that runs the official pgvector image. Kept as the fallback if the Render preconditions fail.
- **Same-origin Vercel rewrite with a first-party cookie, or custom `app.`/`api.` subdomains.** A same-origin Vercel rewrite restores first-party cookies but puts a proxy in the SSE path (buffering risk); custom `app.`/`api.` subdomains avoid the proxy but need a custom domain. Neither is needed for a demo.
- **Cookie-based sessions across sites.** Blocked by Safari ITP. They would also need CSRF defences.
- **Rate limits only, without a spend ledger.** Limits bound requests, not dollars. A worst-case reservation bounds the dollars directly.

## Tradeoffs accepted

- The 2 GB instances cost more than hosted models would on small instances. In return, A3 (no corpus text leaves the system) and deterministic CI hold.
- A token in sessionStorage is readable by any script running on the page. This is mitigated by the strict CSP and the `SafeMarkdown` renderer (no HTML, `img` or `a`; §24), and acceptable for a passcode-gated demo of synthetic data.
- The stream token travels in the URL. It is short-lived, run-scoped, redacted from logs and covered by `no-referrer`.
- Redis-down rate limiting is per instance, so it is weaker across replicas. Limits are tightened to compensate.
- The worst-case reservation under-uses the cap while calls are in flight.
- Platform coupling via `render.yaml`. The containers themselves stay portable.

## Consequences

**Positive**
- One-command, deploy-on-merge infrastructure. Engineering time goes to retrieval, agent and evaluation.
- Auth works in Safari and incognito without third-party cookies.
- LLM spend is bounded by the ledger and by the console limit.

**Negative**
- Single-node Postgres ceiling (§34). Two vendors (Render, Vercel) to operate.
- The AWS path is documented, not exercised, unless built later.

**Follow-ups**
- Record the Phase 0 spike results (pgvector version, role privileges) and the Phase 3 CPU spike numbers (embed and rerank p50/p95, peak RSS) in this ADR.
- Publish the AWS diagram and cost table.

**Verification**
- **Phase 9 exit:** ask → stream → final → reconnect mid-run, tested manually in Safari and in Chrome incognito against the deployed URL, from a clean environment.
- Degradation tests for `BUDGET_EXHAUSTED` (evidence-only) and Redis down (in-process limiter).
- `POLICY_DENIED` on read-only workspaces.
- Route-scoping contract test.
- `/readyz` fails if the app role is superuser or BYPASSRLS.
