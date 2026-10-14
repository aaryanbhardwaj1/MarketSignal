"""Process-local server log ring buffer (developer tools).

A bounded, thread-safe, in-memory copy of the API process's structured log events, read by
``GET /api/dev/logs``. Entries are already sanitized when they arrive (see
``marketsignal.telemetry.server_log_capture``): no request bodies, questions, answers, passages,
tool arguments, prompts, headers or credentials are ever stored here.

* ``seq`` is monotonic for the life of the process; when the buffer is full the oldest entry is
  evicted and ``dropped`` grows, so a poller can detect gaps (``after_seq`` older than
  ``oldest_seq``).
* ``noise`` entries (health checks, metrics, the log endpoint's own polling) live in a separate
  small ring of :data:`NOISE_CAPACITY`, so they can never evict real entries; reads merge both
  rings in ``seq`` order. Evicted noise is not counted in ``dropped``.
* Scope is the API process only: the ingestion worker runs in its own process and its logs never
  reach this buffer (the response says ``scope: "api_process"``).
"""

from __future__ import annotations

import heapq
import threading
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Literal

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LEVEL_RANK = {name: rank for rank, name in enumerate(LEVELS)}
KINDS = ("http", "run", "tool", "verification", "ingestion", "analytics", "app")
STATUS_CLASSES = ("2xx", "3xx", "4xx", "5xx")
DEFAULT_CAPACITY = 2000
NOISE_CAPACITY = 200
DEFAULT_LIMIT = 200
MAX_LIMIT = 500
SCOPE = "api_process"

Scalar = str | int | float | bool | None
Level = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
Kind = Literal["http", "run", "tool", "verification", "ingestion", "analytics", "app"]
StatusClass = Literal["2xx", "3xx", "4xx", "5xx"]


@dataclass(frozen=True, slots=True)
class HttpInfo:
    method: str
    route: str | None
    path: str
    status: int | None
    duration_ms: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "route": self.route,
            "path": self.path,
            "status": self.status,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True, slots=True)
class LogEntry:
    ts: str
    level: str
    logger: str | None
    event: str
    kind: str
    request_id: str | None = None
    run_id: str | None = None
    workspace: str | None = None
    http: HttpInfo | None = None
    fields: Mapping[str, Scalar] = field(default_factory=dict)
    seq: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "level": self.level,
            "logger": self.logger,
            "event": self.event,
            "kind": self.kind,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "workspace": self.workspace,
            "http": None if self.http is None else self.http.to_dict(),
            "fields": dict(self.fields),
        }

    @property
    def noise(self) -> bool:
        return self.fields.get("noise") is True


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ServerLogBuffer:
    """Bounded ring buffer of :class:`LogEntry` with a monotonic ``seq`` (thread-safe)."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self.process_started_at = utc_now_iso()
        self._entries: deque[LogEntry] = deque(maxlen=capacity)
        self._noise: deque[LogEntry] = deque(maxlen=NOISE_CAPACITY)
        self._lock = threading.Lock()
        self._seq = 0
        self._dropped = 0
        self._capture_errors = 0

    def append(self, entry: LogEntry) -> LogEntry:
        """Store ``entry`` with the next ``seq`` (evicting the oldest of its ring when full)."""
        with self._lock:
            self._seq += 1
            stored = replace(entry, seq=self._seq)
            if stored.noise:
                self._noise.append(stored)
                return stored
            if len(self._entries) == self.capacity:
                self._dropped += 1
            self._entries.append(stored)
            return stored

    def note_capture_error(self) -> None:
        with self._lock:
            self._capture_errors += 1

    def snapshot(self) -> tuple[list[LogEntry], int, int]:
        """``(entries oldest first, dropped, capture_errors)`` under the lock."""
        with self._lock:
            merged = list(heapq.merge(self._entries, self._noise, key=lambda e: e.seq))
            return merged, self._dropped, self._capture_errors


_buffer = ServerLogBuffer()
_buffer_lock = threading.Lock()


def get_server_log() -> ServerLogBuffer:
    return _buffer


def configure_server_log(capacity: int) -> ServerLogBuffer:
    """Use a buffer of ``capacity``; an existing buffer of the same size is kept as is."""
    global _buffer
    with _buffer_lock:
        if _buffer.capacity != capacity:
            _buffer = ServerLogBuffer(capacity)
        return _buffer


# --------------------------------------------------------------------------------- queries


@dataclass(frozen=True, slots=True)
class LogQuery:
    level: str | None = None  # minimum level
    kind: str | None = None
    method: str | None = None
    status_class: str | None = None
    route: str | None = None
    q: str | None = None
    include_noise: bool = False
    after_seq: int | None = None
    limit: int = DEFAULT_LIMIT


def _status_class(status: int | None) -> str | None:
    return None if status is None else f"{status // 100}xx"


def _matches_text(entry: LogEntry, needle: str) -> bool:
    http = entry.http
    haystack = (
        entry.event,
        http.route if http else None,
        http.path if http else None,
        entry.request_id,
        entry.run_id,
    )
    return any(needle in value.lower() for value in haystack if value)


def _matches(entry: LogEntry, query: LogQuery, *, check_level: bool = True) -> bool:
    checks = (
        query.include_noise or not entry.noise,
        not check_level
        or query.level is None
        or LEVEL_RANK.get(entry.level, 1) >= LEVEL_RANK[query.level],
        query.kind is None or entry.kind == query.kind,
        query.method is None or (entry.http is not None and entry.http.method == query.method),
        query.status_class is None
        or (entry.http is not None and _status_class(entry.http.status) == query.status_class),
        query.route is None or (entry.http is not None and entry.http.route == query.route),
        query.after_seq is None or entry.seq > query.after_seq,
        not query.q or _matches_text(entry, query.q.lower()),
    )
    return all(checks)


def query_logs(buffer: ServerLogBuffer, query: LogQuery) -> dict[str, Any]:
    """The ``ServerLogResponse`` for ``query``.

    Newest first, unless ``after_seq`` is given (incremental polling): then ascending, the
    ``limit`` entries right after ``after_seq``. ``levels`` counts entries matching every filter
    except ``level``; ``routes`` lists every route template in the buffer.
    """
    entries, dropped, capture_errors = buffer.snapshot()
    levels = dict.fromkeys(LEVELS, 0)
    selected: list[LogEntry] = []
    for entry in entries:
        if not _matches(entry, query, check_level=False):
            continue
        levels[entry.level] = levels.get(entry.level, 0) + 1
        if _matches(entry, query):
            selected.append(entry)
    page = selected[: query.limit] if query.after_seq is not None else selected[::-1][: query.limit]
    routes = sorted({e.http.route for e in entries if e.http is not None and e.http.route})
    return {
        "entries": [e.to_dict() for e in page],
        "capacity": buffer.capacity,
        "size": len(entries),
        "dropped": dropped,
        "capture_errors": capture_errors,
        "oldest_seq": entries[0].seq if entries else None,
        "latest_seq": entries[-1].seq if entries else None,
        "process_started_at": buffer.process_started_at,
        "scope": SCOPE,
        "routes": routes,
        "levels": levels,
    }
