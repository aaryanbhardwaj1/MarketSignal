"""Capability tokens (plan §17; ADR-0006): HS256 pinned, aud=mcp, iss, ±5 s skew, no details."""

from __future__ import annotations

import time
import uuid
from typing import Any

import jwt
import pytest
from pydantic import SecretStr

from marketsignal.tools.capability import (
    AUDIENCE,
    ISSUER,
    UnauthenticatedError,
    issue,
    verify,
)

KEY = SecretStr("test-only-capability-key-0123456789abcdef")
OTHER = SecretStr("test-only-other-capability-key-0123456789")
WS = uuid.uuid4()
RUN = uuid.uuid4()


def _issue(**overrides: Any) -> str:
    kwargs: dict[str, Any] = {
        "run_id": RUN,
        "workspace_id": WS,
        "workspace_code": "ACME",
        "principal": "demo-user",
        "persona": "analyst",
        "tools": ["search_evidence", "get_evidence"],
        "max_conf": "confidential",
        "ttl_s": 60,
    }
    kwargs.update(overrides)
    return issue(KEY, **kwargs)


def _raw(claims: dict[str, Any], key: str = KEY.get_secret_value(), alg: str = "HS256") -> str:
    now = int(time.time())
    base = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "demo-user",
        "jti": str(RUN),
        "iat": now,
        "nbf": now,
        "exp": now + 60,
        "ws": str(WS),
        "wsc": "ACME",
        "persona": "analyst",
        "tools": ["search_evidence"],
        "max_conf": "internal",
    }
    base.update(claims)
    return jwt.encode(base, key, algorithm=alg)


def test_round_trip_builds_context_from_claims() -> None:
    ctx = verify(KEY, _issue())
    assert ctx.workspace_id == str(WS)
    assert ctx.workspace_code == "ACME"
    assert ctx.run_id == str(RUN)
    assert ctx.principal == "demo-user"
    assert ctx.persona == "analyst"
    assert ctx.tools == frozenset({"search_evidence", "get_evidence"})
    assert ctx.max_confidentiality == "confidential"


def test_run_id_is_optional() -> None:
    assert verify(KEY, _issue(run_id=None)).run_id is None


def test_claims_shape() -> None:
    claims = jwt.decode(_issue(), options={"verify_signature": False})
    assert claims["aud"] == "mcp"
    assert claims["iss"] == "marketsignal-api"
    assert claims["jti"] == str(RUN)
    assert claims["sub"] == "demo-user"
    assert {"iat", "nbf", "exp", "ws", "wsc", "persona", "tools", "max_conf"} <= set(claims)
    assert jwt.get_unverified_header(_issue())["alg"] == "HS256"


def test_skew_leeway_is_five_seconds() -> None:
    now = time.time()
    token = _issue(ttl_s=10)
    verify(KEY, token, now=now + 14)  # exp + 4 s: inside the leeway
    with pytest.raises(UnauthenticatedError):
        verify(KEY, token, now=now + 17)


@pytest.mark.parametrize(
    "token",
    [
        "",
        "not-a-jwt",
        _raw({"aud": "sse"}),
        _raw({"iss": "someone-else"}),
        _raw({"exp": int(time.time()) - 60, "iat": int(time.time()) - 120}),
        _raw({"nbf": int(time.time()) + 120}),
        _raw({}, key=OTHER.get_secret_value()),
        _raw({}, alg="HS512"),
        _raw({"ws": "not-a-uuid"}),
        _raw({"tools": "search_evidence"}),
        _raw({"max_conf": "top-secret"}),
        _raw({"wsc": ""}),
    ],
    ids=[
        "empty",
        "garbage",
        "wrong-audience",
        "wrong-issuer",
        "expired",
        "not-yet-valid",
        "wrong-key",
        "unpinned-alg",
        "bad-workspace",
        "tools-not-list",
        "bad-confidentiality",
        "empty-workspace-code",
    ],
)
def test_rejections_carry_no_details(token: str) -> None:
    with pytest.raises(UnauthenticatedError) as info:
        verify(KEY, token)
    assert str(info.value) == "unauthenticated"


def test_missing_required_claim_is_rejected() -> None:
    claims = jwt.decode(_issue(), options={"verify_signature": False})
    del claims["ws"]
    with pytest.raises(UnauthenticatedError):
        verify(KEY, jwt.encode(claims, KEY.get_secret_value(), algorithm="HS256"))


def test_issue_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError, match="ttl_s"):
        _issue(ttl_s=0)
    with pytest.raises(ValueError, match="unknown tool"):
        _issue(tools=["drop_tables"])
