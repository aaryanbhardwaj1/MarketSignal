"""Test-session configuration.

Integration tests run against a dedicated database (default ``marketsignal_test``, created by
``db/init/01_roles.sh``), never the development database. This hook rewrites every database URL
before any settings object is created. CI sets ``MS_TEST_DATABASE`` to its own fresh database.
"""

from __future__ import annotations

import os
import re

import pytest

_URL_VARS = ("MS_DATABASE_URL", "MS_MIGRATIONS_DATABASE_URL", "MS_TEST_SUPERUSER_DATABASE_URL")
_DEFAULTS = {
    "MS_DATABASE_URL": "postgresql+psycopg://ms_app:dev-only-insecure-app@localhost:5432/marketsignal",
    "MS_MIGRATIONS_DATABASE_URL": "postgresql+psycopg://ms_owner:dev-only-insecure-owner@localhost:5432/marketsignal",
}


def _with_database(url: str, database: str) -> str:
    return re.sub(r"/[^/?]+(\?|$)", f"/{database}\\1", url, count=1) if "://" in url else url


def pytest_configure(config: pytest.Config) -> None:
    database = os.environ.get("MS_TEST_DATABASE", "marketsignal_test")
    for var in _URL_VARS:
        value = os.environ.get(var) or _DEFAULTS.get(var)
        if value:
            scheme, rest = value.split("://", 1)
            os.environ[var] = f"{scheme}://{_with_database(rest, database)}"
    os.environ.setdefault("MS_ENV", "test")
    os.environ.setdefault("MS_LOG_JSON", "false")
