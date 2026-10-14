# ADR-0023: Developer server log as a sanitized, process-local ring buffer

- **Status:** Accepted
- **Date:** 2026-10-14
- **Implementation:** Built in the final phase. Buffer `devtools/server_log.py`; capture and sanitizer `telemetry/server_log_capture.py`; access events `telemetry/access_log.py` (`AccessLogMiddleware`); logging wiring `telemetry/logging.py`; endpoint `api/routers/logs.py` (`GET /api/dev/logs`); setting `MS_SERVER_LOG_CAPACITY`.
- **Related:** ADR-0009 (workspace isolation), ADR-0014 (principals, not built), ADR-0016 (purge)

## Context

The Telemetry tools read persisted runs, but a developer debugging the demo also needs to see what the API process is doing: requests, statuses, durations, warnings and errors. Structured logs already go to stdout. The question is how to show them in the developer UI without creating a new store of user content: questions, answers and passages are tenant data that purge must be able to remove (ADR-0016), and request paths and headers can carry tokens.

## Decision

**An in-memory ring buffer in the API process, fed by a sanitizer, readable only where the developer routes are mounted.**

- **Capture.** A structlog processor (after `redact_sensitive`, before the renderer) and a stdlib handler for WARNING+ records copy each event into the buffer. Capture never raises and never changes stdout output; an internal failure only increments `capture_errors`.
- **What is kept.** Ids, enums, counts and durations. Dropped: questions, queries, answers, passages, prompts, tool arguments, request bodies, headers, query strings, tokens, keys, DSNs and URLs, tracebacks, and every non-scalar value. Kept strings are truncated (200 characters), keys are capped (12 fields), and the shared credential scrubber runs over everything kept.
- **Linear-time scrubbing.** Each string is cut to a 512-character window before scrubbing, so the work per value is bounded however long the client-controlled input is.
- **Access events.** One `http.request` event per request, logged when the response (or SSE stream) finishes, with method, route template, path without query string, status, duration and request id. Control characters in the path are replaced and the path is capped at 512 characters. Health, metrics and the log endpoint's own polling are marked noise and kept in a separate small ring so they never evict real entries.
- **Process-local and bounded.** Capacity `MS_SERVER_LOG_CAPACITY` (default 2,000, at most 10,000). `seq` is monotonic; evictions increase `dropped`, so a poller can detect gaps. The ingestion worker's logs never reach it (`scope: "api_process"`). Nothing is written to the database or disk.
- **Gated.** Capture is switched on, and `GET /api/dev/logs` is mounted, only when `env != "prod"` and `dev_endpoints_enabled`. The endpoint is not workspace-scoped; it is a process-level developer tool, never a product endpoint.

## Alternatives considered

- **A persisted log table.** Survives restarts and could be queried across processes. It would be a new store holding request metadata across tenants, needing retention, RLS and purge integration, for a developer convenience. Rejected for privacy and scope.
- **Reading stdout or a log file.** No new code path, but the stdout stream is not sanitized for display, and parsing it back is fragile. Rejected.
- **A hosted log service.** The right answer for a deployment, but out of scope for a local demo and would ship data off the machine. Deferred with deployment (ADR-0014).

## Tradeoffs accepted

- **Lost on restart** and limited to the most recent entries; it is a live view, not an audit trail.
- **API process only.** Worker logs and other processes are not visible.
- **Sanitization drops useful detail.** A failing request shows its route, status and duration, not its body; detail stays in stdout.

## Consequences

**Positive**
- Developers see live server activity in the Telemetry tools without any new store of user content.
- Bounded memory and bounded per-event work, whatever the input.

**Negative**
- Two lists of sensitive key names to keep in step (stdout redaction and the capture sanitizer).

**Verification**
- `tests/unit/test_server_log.py`, `tests/unit/test_server_log_api.py`, `tests/integration/test_server_log_telemetry_series.py`.
