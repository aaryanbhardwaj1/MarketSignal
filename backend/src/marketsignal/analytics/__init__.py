"""Deterministic structured analytics (Phase 5; plan §18, ADR-0006).

* ``schema``   - the analysable datasets of a workspace (active versions only) and unit inference.
* ``validate`` - a request checked against the dataset's stored column profile -> a plan.
* ``engine``   - pure, deterministic computation over the version's rows (Decimal, half-even).
* ``rounding`` - the rounding rules the verifier relies on.
* ``store``    - the parameterized row fetch and the ``analytics_results`` write.

The model chooses *what* to compute; this package computes it. Column names and values are
never interpolated into SQL: rows are fetched by table id and filtered in Python.
"""
