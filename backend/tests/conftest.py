"""Test-session configuration.

Integration tests run against a dedicated database (default ``marketsignal_test``, created by
``db/init/01_roles.sh``), never the development database. This hook rewrites every database URL
before any settings object is created. CI sets ``MS_TEST_DATABASE`` to its own fresh database.
"""

from __future__ import annotations

import os

import pytest

_URL_VARS = ("MS_DATABASE_URL", "MS_MIGRATIONS_DATABASE_URL", "MS_TEST_SUPERUSER_DATABASE_URL")
_DEFAULTS = {
    "MS_DATABASE_URL": "postgresql+psycopg://ms_app:dev-only-insecure-app@localhost:5432/marketsignal",
    "MS_MIGRATIONS_DATABASE_URL": "postgresql+psycopg://ms_owner:dev-only-insecure-owner@localhost:5432/marketsignal",
}


def with_database(url: str, database: str) -> str:
    """Replace the database name (last path segment) of a DSN, keeping any query string."""
    head, sep, tail = url.rpartition("/")
    if not sep or "@" not in head:
        return url
    _, qsep, query = tail.partition("?")
    return f"{head}/{database}{qsep}{query}"


def pytest_configure(config: pytest.Config) -> None:
    database = os.environ.get("MS_TEST_DATABASE", "marketsignal_test")
    for var in _URL_VARS:
        value = os.environ.get(var) or _DEFAULTS.get(var)
        if value:
            os.environ[var] = with_database(value, database)
    os.environ.setdefault("MS_ENV", "test")
    os.environ.setdefault("MS_LOG_JSON", "false")
