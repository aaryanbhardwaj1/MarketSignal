"""Governed research tools: contract, registry, transports (plan §17-18; ADR-0006)."""

# The analytics contract builds on ``contracts._In``/``_Out`` and ``contracts`` re-exports the
# analytics models: load ``contracts`` first so the import cycle always resolves the same way.
from marketsignal.tools import contracts as _contracts  # noqa: F401
