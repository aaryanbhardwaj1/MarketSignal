"""Grounded presentation decks built from the curated analyst brief.

* ``models``   - the request body and the business labels for statuses and claim types.
* ``sources``  - numbers each cited passage or analysis once, deck-wide.
* ``composer`` - turns the re-verified brief and analyses into slides, deterministically. It
  never adds a claim that is not in the selected items: unverified items are excluded, stale or
  withdrawn references never appear, and interpretive claims keep a visible label.
* ``render``   - draws the composed deck as a 16:9 PowerPoint file in memory (``theme`` holds
  the colours, fonts and geometry).
* ``filename`` - a safe ASCII download name.

Nothing here calls a language model or writes to disk or the database.
"""
