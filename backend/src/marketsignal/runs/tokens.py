"""Short-lived SSE stream tokens (ADR-0008, ADR-0014).

``EventSource`` cannot send an ``Authorization`` header, so the stream URL carries ``?st=``: an
HS256 JWT with ``aud=sse`` bound to one run and one workspace, expiring at the run's maximum
duration plus the replay window. The token is redacted from logs (structlog redaction list)
and responses send ``Referrer-Policy: no-referrer``. A token for another workspace or run is
rejected as not found.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import jwt

AUDIENCE = "sse"
ALGORITHM = "HS256"


class InvalidStreamTokenError(ValueError):
    """Missing, expired, malformed or mismatched stream token."""


@dataclass(frozen=True, slots=True)
class StreamClaims:
    run_id: uuid.UUID
    workspace_code: str
    subject: str


def issue(secret: str, *, run_id: uuid.UUID, workspace_code: str, subject: str, ttl_s: int) -> str:
    now = int(time.time())
    claims = {
        "aud": AUDIENCE,
        "run_id": str(run_id),
        "ws": workspace_code,
        "sub": subject,
        "iat": now,
        "exp": now + ttl_s,
    }
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def verify(secret: str, token: str, *, run_id: uuid.UUID, workspace_code: str) -> StreamClaims:
    try:
        claims = jwt.decode(token, secret, algorithms=[ALGORITHM], audience=AUDIENCE)
    except jwt.PyJWTError as exc:
        raise InvalidStreamTokenError("invalid stream token") from exc
    if claims.get("run_id") != str(run_id) or claims.get("ws") != workspace_code:
        raise InvalidStreamTokenError("stream token does not match this run")
    return StreamClaims(run_id, workspace_code, str(claims.get("sub", "")))
