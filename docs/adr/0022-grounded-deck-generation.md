# ADR-0022: Grounded deck generation from the verified brief, composed and rendered on the server

- **Status:** Accepted
- **Date:** 2026-10-14
- **Implementation:** Built in the final phase. Router `api/routers/decks.py` (`POST /api/workspaces/{ws}/decks/preview`, `POST /api/workspaces/{ws}/decks/pptx`); composition `decks/composer.py`, `decks/grounding.py`, `decks/quant.py`, `decks/sources.py`; rendering `decks/render.py`, `render_blocks.py`, `render_text.py`, `theme.py`; request model `decks/models.py`.
- **Related:** ADR-0020 (deterministic analytics), [`SYSTEM_DESIGN.md` §10](../SYSTEM_DESIGN.md#10-product-and-developer-surfaces-final-phase) (curated brief v2)

## Context

Strategy users finish in slides. The product already has a curated analyst brief whose quotes are re-resolved and whose figures are recomputed on every request (Insights, Growth Opportunities, Analytics). A deck must not weaken that guarantee: every sentence and number on a slide has to be something the brief already verified on this request, and the system must make no live model calls.

## Decision

**Compose decks deterministically from the re-verified brief on the server, and render `.pptx` with python-pptx.**

- **Same source as the pages.** Both endpoints read the same re-verified brief and recomputed analyses as `GET /insights` (same request-time verification and cache). Nothing is persisted and no model is called. The workspace comes from the trusted scope only.
- **Selection, not authoring.** The request names signal, opportunity and analysis ids (bounded: 30, 10 and 10). Ids not in this workspace's brief are `422 DECK_ITEMS_NOT_FOUND`. Items are taken in the brief's curated order.
- **Fail-closed grounding per item.** Unverified items, analyses that did not recompute, and items whose main claim lost its grounding are excluded and reported in `excluded` with a plain reason. A claim survives only if: observed or forecast → at least one verified supporting passage; derived → at least one computed metric; inference or hypothesis → a verified passage or a computed metric. A forecast on an item that is not fully verified is shown as a hypothesis. A download whose every selected item was excluded is `422 DECK_EMPTY`.
- **No new text.** Slide text is copied from the selected items, except fixed section titles, status labels and evidence counts. Inference, Hypothesis and Forecast claims carry a visible tag. Each bullet cites numbered sources; speaker notes list the slide's sources with their handles for audit, slide text never shows a handle or an internal id, and an appendix lists all sources.
- **Fixed structure.** Title, executive summary, key customer findings, quantitative evidence, competitor and market findings, one slide per growth opportunity, risks and blockers, recommended next steps, appendix. Empty sections are omitted; long ones continue on `(cont.)` slides.
- **Deterministic, bounded output.** 16:9, blank layout with the same chrome on every slide, rendered in memory. Zip timestamps and document properties are fixed, so the same deck renders to the same bytes. At most 150 slides and 15 MB (`422 DECK_TOO_LARGE`). The download is `Cache-Control: no-store` with `nosniff`.
- **Preview first.** `/decks/preview` returns the composed deck as JSON so the UI can show slides and exclusions before the download.

## Alternatives considered

- **LLM-written decks.** Fluent summaries and titles. Model-written slide text would need its own verification pass, could introduce figures the brief never computed, and needs live calls. Rejected for grounding.
- **Client-side generation (PptxGenJS).** No server work. The grounding rules would then live in browser code that any client could bypass, and it would add a frontend runtime dependency, while python-pptx was already a backend dependency for ingestion. Rejected so grounding is enforced server-side.
- **Persisted decks.** A stored deck would go stale when sources are superseded or purged. Decks are recomposed on request instead.

## Tradeoffs accepted

- **Fixed template.** Users cannot reorder sections, edit text or restyle slides in the product; they edit the downloaded file.
- **Deck quality is bounded by the brief.** Only curated items can appear; there is no deck for an arbitrary chat answer.
- **Exclusions can surprise.** An item visible on Insights as "Could not be re-verified" is left out of the deck; the preview lists it with the reason.

## Consequences

**Positive**
- The deck carries the same guarantee as the pages: nothing on a slide is newer or less verified than the brief on this request.
- Reproducible bytes make the renderer testable by content, not by eye.

**Negative**
- A second rendering path (PowerPoint) to keep in line with the web design rules.

**Verification**
- `tests/unit/test_deck_composer.py`, `tests/unit/test_deck_render.py`, `tests/integration/test_decks_api.py`.
