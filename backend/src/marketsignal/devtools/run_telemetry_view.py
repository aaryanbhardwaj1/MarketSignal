"""Pure views for run telemetry: cost estimate, keyset cursor, allowlisted run/agent/route
views, verification summaries and the event timeline. No I/O; see ``run_telemetry``.

Content rules: the timeline never carries token text, answer content, citation cards or draft
text; verification summaries never carry rejected spans; the agent record is an allowlist (no
model reasoning is stored anywhere, and none is returned).
"""

from __future__ import annotations

import base64
import binascii
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# List prices in USD per million tokens. They mirror the evaluation harness's prices
# (``Settings.llm_price_*_per_mtok`` as applied by ``evaluation.grounded_stats._token_cost``),
# so telemetry and evaluation estimates agree. Estimates only: no cost is ever persisted.
PRICE_INPUT_PER_MTOK = 2.0
PRICE_OUTPUT_PER_MTOK = 10.0
PRICE_CACHE_WRITE_PER_MTOK = 2.5
PRICE_CACHE_READ_PER_MTOK = 0.2
_PER_MTOK = 1_000_000


_AGENT_KEYS = (
    "stop_reason",
    "steps",
    "tool_calls",
    "tool_errors",
    "pool_size",
    "sufficient",
    "gap_count",
    "duration_ms",
    "flags",
    "usage",
)
_ROUTE_KEYS = ("requested", "persona_default", "decided", "reason", "cues", "task_type")
_REDACTED_ARGS = {"redacted": True}


def pct(p50: Any, p95: Any, n: Any) -> dict[str, Any]:
    return {
        "p50": None if p50 is None else round(float(p50), 1),
        "p95": None if p95 is None else round(float(p95), 1),
        "n": int(n or 0),
    }


def estimate_cost_usd(tokens: Mapping[str, float]) -> float:
    """List-price estimate for ``{input, output, cache_read, cache_write}`` token counts."""
    usd = (
        tokens.get("input", 0) * PRICE_INPUT_PER_MTOK
        + tokens.get("output", 0) * PRICE_OUTPUT_PER_MTOK
        + tokens.get("cache_write", 0) * PRICE_CACHE_WRITE_PER_MTOK
        + tokens.get("cache_read", 0) * PRICE_CACHE_READ_PER_MTOK
    ) / _PER_MTOK
    return round(usd, 6)


def cost_estimate(totals: Mapping[str, float], n_runs_with_usage: int) -> dict[str, Any]:
    total = estimate_cost_usd(totals) if n_runs_with_usage else None
    return {
        "total_usd": total,
        "per_run_usd": round(total / n_runs_with_usage, 6) if total is not None else None,
        "n_runs_with_usage": n_runs_with_usage,
        "prices_per_mtok": {
            "input": PRICE_INPUT_PER_MTOK,
            "output": PRICE_OUTPUT_PER_MTOK,
            "cache_write": PRICE_CACHE_WRITE_PER_MTOK,
            "cache_read": PRICE_CACHE_READ_PER_MTOK,
        },
        "basis": "list_prices_from_persisted_usage",
    }


def encode_cursor(created_at: datetime, run_id: uuid.UUID | str) -> str:
    raw = f"{created_at.isoformat()}|{run_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    """Inverse of :func:`encode_cursor`; raises ``ValueError`` for anything malformed."""
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("malformed cursor") from exc
    stamp, sep, ident = raw.partition("|")
    if not sep:
        raise ValueError("malformed cursor")
    created_at = datetime.fromisoformat(stamp)
    if created_at.tzinfo is None:
        raise ValueError("cursor timestamp must be timezone-aware")
    return created_at, uuid.UUID(ident)


def is_redacted_args(args: Any) -> bool:
    return bool(args == _REDACTED_ARGS)


def agent_view(agent: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The stored agent record minus its trace, as an allowlist (``states`` always a list)."""
    if not agent:
        return None
    view = {key: agent[key] for key in _AGENT_KEYS if key in agent}
    states = agent.get("states")
    view["states"] = [str(s) for s in states] if isinstance(states, list) else []
    return view


def route_view(route: Mapping[str, Any] | None) -> dict[str, Any]:
    return {key: route[key] for key in _ROUTE_KEYS if route and key in route}


def numeric_only(record: Mapping[str, Any] | None) -> dict[str, float]:
    return {
        key: value
        for key, value in (record or {}).items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }


def verification_summary(row: Sequence[Any]) -> dict[str, Any]:
    """``VerificationAttemptSummary`` from the pre-stripped SQL row (no rejected spans)."""
    attempt, disposition, passed, citations, categories, repairs_n, rejected, result_ids = row
    return {
        "attempt": int(attempt),
        "disposition": disposition,
        "passed": bool(passed),
        "citations": int(citations) if isinstance(citations, (int, float)) else 0,
        "failure_categories": [str(c) for c in categories or []],
        "repairs_n": int(repairs_n or 0),
        "rejected": [
            {
                "reason": str(item.get("reason") or ""),
                "section": item.get("section") if isinstance(item.get("section"), str) else None,
                "aliases": [str(a) for a in item.get("aliases") or []],
            }
            for item in rejected or []
            if isinstance(item, dict)
        ],
        "result_ids": [str(r) for r in result_ids or []],
    }


# --- timeline -------------------------------------------------------------------------------


@dataclass(frozen=True)
class EventRow:
    seq: int
    type: str
    t_ms: float
    payload: Mapping[str, Any]


def _pick(payload: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    return {key: payload[key] for key in keys if key in payload}


def _entry(t_ms: float, kind: str, label: str, detail: dict[str, Any] | None) -> dict[str, Any]:
    return {"t_ms": round(t_ms, 1), "kind": kind, "label": label, "detail": detail}


def _event_entry(event: EventRow) -> dict[str, Any] | None:
    """One timeline entry for a non-streaming event, from an allowlist of payload fields."""
    p = event.payload
    match event.type:
        case "run_started":
            return _entry(event.t_ms, "run_started", "Run started", _pick(p, "mode", "persona"))
        case "status":
            return _entry(
                event.t_ms, "status", str(p.get("message") or "status"), _pick(p, "phase")
            )
        case "tool_started":
            detail = _pick(p, "step", "call_index", "tool", "kind")
            return _entry(
                event.t_ms, "tool_started", str(p.get("summary") or p.get("tool")), detail
            )
        case "tool_completed":
            detail = _pick(p, "step", "call_index", "tool", "status", "duration_ms", "result_count")
            label = f"{p.get('tool', 'tool')} {p.get('status', 'completed')}"
            return _entry(event.t_ms, "tool_completed", label, detail)
        case "evidence":
            detail = _pick(p, "item_count", "result_count", "truncated", "classes")
            label = f"Evidence pack: {p.get('item_count', 0)} passages"
            return _entry(event.t_ms, "evidence", label, detail)
        case "draft_reset":
            label = f"Draft reset: {p.get('reason', 'unknown')}"
            return _entry(event.t_ms, "draft_reset", label, _pick(p, "attempt", "reason"))
        case "warning" | "error":
            detail = _pick(p, "code", "retryable")
            return _entry(event.t_ms, event.type, str(p.get("code") or event.type), detail)
        case "final":
            return _entry(event.t_ms, "final", "Answer finalized", _pick(p, "citations", "passed"))
        case "done":
            label = f"Done: {p.get('termination_state') or 'unknown'}"
            return _entry(event.t_ms, "done", label, _pick(p, "termination_state", "flags"))
    return None


def build_timeline(events: Iterable[EventRow]) -> list[dict[str, Any]]:
    """Ordered timeline. Token and citation events are folded into one ``tokens`` entry per
    synthesis attempt (count, citations, last offset); no streamed text is ever included."""
    timeline: list[dict[str, Any]] = []
    streams: dict[Any, dict[str, Any]] = {}
    for event in sorted(events, key=lambda e: e.seq):
        if event.type in ("token", "citation"):
            attempt = event.payload.get("attempt")
            stream = streams.get(attempt)
            if stream is None:
                detail = {"count": 0, "citations": 0, "attempt": attempt, "last_t_ms": 0.0}
                stream = _entry(event.t_ms, "tokens", "", detail)
                streams[attempt] = stream
                timeline.append(stream)
            stream["detail"]["count" if event.type == "token" else "citations"] += 1
            stream["detail"]["last_t_ms"] = round(event.t_ms, 1)
            continue
        entry = _event_entry(event)
        if entry is not None:
            timeline.append(entry)
    for stream in streams.values():
        stream["label"] = f"Streamed {stream['detail']['count']} chunks"
    return timeline


def event_offset_ms(payload: Mapping[str, Any], created_at: datetime, run_start: datetime) -> float:
    """Milliseconds since the run was created: the event's own ``ts`` (wall clock at emit) when
    present and valid, else the row's ``created_at``."""
    stamp = created_at
    ts = payload.get("ts")
    if isinstance(ts, str):
        try:
            parsed = datetime.fromisoformat(ts)
        except ValueError:
            parsed = None
        if parsed is not None and parsed.tzinfo is not None:
            stamp = parsed
    return (stamp - run_start).total_seconds() * 1000
