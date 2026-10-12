"""Curated analyst brief (final productization phase).

* ``fixture``   - the versioned, hand-authored brief (signals, opportunities, named analyses) and
  its strict schema; one JSON file per workspace under ``fixtures/``.
* ``evidence``  - re-resolves every quoted passage against current evidence (verified, stale or
  withdrawn).
* ``analyses``  - recomputes every named analysis with the deterministic analytics engine and
  compares it to the curated value (computed, mismatch or unavailable). Never persists.
* ``service``   - assembles the brief and the analyses responses, with a small in-process cache.

Nothing here calls a language model or writes to the database.
"""
