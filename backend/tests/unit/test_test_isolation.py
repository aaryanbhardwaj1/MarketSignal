"""Guard: the test session must never point at the development database."""

from __future__ import annotations

import os

from marketsignal.config import get_settings
from tests.conftest import with_database


def test_session_uses_the_dedicated_test_database() -> None:
    expected = "/" + os.environ.get("MS_TEST_DATABASE", "marketsignal_test")
    settings = get_settings()
    assert settings.database_url.get_secret_value().endswith(expected)
    assert settings.migrations_database_url.get_secret_value().endswith(expected)


def test_with_database_rewrites_only_the_database_name() -> None:
    url = "postgresql+psycopg://u:p@host:5432/marketsignal"
    assert with_database(url, "x_test") == "postgresql+psycopg://u:p@host:5432/x_test"
    assert (
        with_database(url + "?sslmode=require", "t")
        == "postgresql+psycopg://u:p@host:5432/t?sslmode=require"
    )
    assert with_database("not a url", "t") == "not a url"
