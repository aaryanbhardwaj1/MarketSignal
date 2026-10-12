"""Package behind ``scripts/build_eval_catalog.py`` (stdlib only)."""

from .builder import build, dump
from .common import DEFAULT_OUT, REPO

__all__ = ["DEFAULT_OUT", "REPO", "build", "dump"]
