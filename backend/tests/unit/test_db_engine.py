"""The engine must never put bound parameters (answer/evidence text) into error strings."""

from __future__ import annotations

from pydantic import SecretStr

from marketsignal.config import Settings
from marketsignal.db.engine import create_engine


def test_engine_hides_bound_parameters() -> None:
    settings = Settings(
        env="test",
        database_url=SecretStr("postgresql+psycopg://ms_app:x@127.0.0.1:1/marketsignal"),
        redis_url=None,
        stream_token_secret=SecretStr("unit-test-stream-token-secret-0123456789"),
    )  # type: ignore[call-arg]
    engine = create_engine(settings)
    assert engine.sync_engine.hide_parameters is True
