"""Run-scoped capability tokens for the governed tools (plan §17; ADR-0006).

The API mints one token per research run; the tool layer verifies it on every call and builds
the ``ToolContext`` from its claims only. HS256 with a dedicated key, the algorithm pinned
(the token's own ``alg`` header is never trusted), ``aud=mcp``, ``iss=marketsignal-api``,
``iat``/``nbf``/``exp`` with ±5 s leeway, ``jti`` = run id, ``sub`` = principal, ``ws``
(workspace uuid), ``wsc`` (workspace code), ``persona``, ``tools``, ``max_conf`` and, when the
run is restricted to some source classes, ``classes`` (absent = every class).

``verify`` is never looser than ``issue``: ``jti`` (the run id, which makes the token revocable)
is required, the lifetime ``exp - iat`` may not exceed ``MAX_TTL_S`` and ``iat`` may not lie in
the future (beyond the leeway).

Every failure raises :class:`UnauthenticatedError` with the fixed message ``unauthenticated``:
no reason, claim or token text ever reaches a caller, log or model.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterable
from typing import Any

import jwt
from pydantic import SecretStr

from marketsignal.domain.enums import Confidentiality, SourceClass
from marketsignal.tools.contracts import TOOL_NAMES, ToolContext

ALGORITHM = "HS256"
AUDIENCE = "mcp"
ISSUER = "marketsignal-api"
LEEWAY_S = 5
MAX_TTL_S = 3600
_REQUIRED = ["exp", "iat", "nbf", "aud", "iss", "sub", "jti", "ws", "wsc", "tools", "max_conf"]
_CONFIDENTIALITY = {c.value for c in Confidentiality}
_SOURCE_CLASSES = {c.value for c in SourceClass}


class UnauthenticatedError(Exception):
    """The credential is missing, malformed, forged, expired or revoked. No details."""

    def __init__(self) -> None:
        super().__init__("unauthenticated")


def issue(
    key: SecretStr,
    *,
    run_id: uuid.UUID | str,
    workspace_id: uuid.UUID | str,
    workspace_code: str,
    principal: str,
    persona: str,
    tools: Iterable[str],
    max_conf: str,
    ttl_s: float,
    source_classes: Iterable[str] = (),
) -> str:
    """Mint a capability token; ``exp`` should be the run deadline (``ttl_s`` from now).
    ``source_classes`` restricts every tool to those classes (empty = unrestricted)."""
    if run_id is None:
        raise ValueError("run_id is required (tokens must be revocable)")
    granted = sorted(set(tools))
    classes = sorted({str(c) for c in source_classes})
    if any(c not in _SOURCE_CLASSES for c in classes):
        raise ValueError("unknown source class")
    if not 0 < ttl_s <= MAX_TTL_S:
        raise ValueError("ttl_s out of range")
    if any(t not in TOOL_NAMES for t in granted):
        raise ValueError("unknown tool in grant")
    if max_conf not in _CONFIDENTIALITY:
        raise ValueError("unknown confidentiality")
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": principal,
        "iat": now,
        "nbf": now,
        "exp": now + max(1, int(ttl_s)),
        "ws": str(uuid.UUID(str(workspace_id))),
        "wsc": workspace_code,
        "persona": persona,
        "tools": granted,
        "max_conf": max_conf,
        "jti": str(uuid.UUID(str(run_id))),
    }
    if classes:
        claims["classes"] = classes
    return jwt.encode(claims, key.get_secret_value(), algorithm=ALGORITHM)


def verify(key: SecretStr, token: str, *, now: float | None = None) -> ToolContext:
    """Verify signature and claims; return the trusted context. Raises UnauthenticatedError."""
    if not token or len(token) > 8192:
        raise UnauthenticatedError()
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            key.get_secret_value(),
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
            leeway=LEEWAY_S,
            # Time claims are checked below against one clock (``now`` for tests).
            options={
                "require": _REQUIRED,
                "verify_exp": False,
                "verify_nbf": False,
                "verify_iat": False,
            },
        )
    except (jwt.PyJWTError, TypeError, ValueError):
        raise UnauthenticatedError() from None
    return _context(claims, time.time() if now is None else now)


def _context(claims: dict[str, Any], now: float) -> ToolContext:
    try:
        exp, iat = float(claims["exp"]), float(claims["iat"])
        if exp + LEEWAY_S < now or float(claims["nbf"]) - LEEWAY_S > now:
            raise UnauthenticatedError()
        if iat - LEEWAY_S > now or exp - iat > MAX_TTL_S + LEEWAY_S:
            raise UnauthenticatedError()
        tools = claims["tools"]
        if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
            raise UnauthenticatedError()
        code = claims["wsc"]
        if not isinstance(code, str) or not code:
            raise UnauthenticatedError()
        if claims["max_conf"] not in _CONFIDENTIALITY:
            raise UnauthenticatedError()
        classes = claims.get("classes", [])
        if not isinstance(classes, list) or any(c not in _SOURCE_CLASSES for c in classes):
            raise UnauthenticatedError()
        return ToolContext(
            workspace_id=str(uuid.UUID(str(claims["ws"]))),
            workspace_code=code,
            run_id=str(uuid.UUID(str(claims["jti"]))),
            principal=str(claims["sub"]),
            persona=str(claims.get("persona", "")),
            tools=frozenset(tools),
            max_confidentiality=str(claims["max_conf"]),
            source_classes=frozenset(str(c) for c in classes),
        )
    except (KeyError, TypeError, ValueError):
        raise UnauthenticatedError() from None
