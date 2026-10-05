/**
 * Splits parent text into before / mark / after using the API's character offsets.
 * Offsets come from the Python backend and count Unicode code points, so text containing
 * astral characters (emoji, some CJK) is sliced by code point rather than UTF-16 unit.
 */

export interface HighlightSegments {
  before: string;
  mark: string;
  after: string;
  /** False when offsets were missing, inverted or entirely outside the text. */
  valid: boolean;
}

const ASTRAL = /[\uD800-\uDBFF][\uDC00-\uDFFF]/;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function segmentHighlight(
  text: string,
  charStart: number | null | undefined,
  charEnd: number | null | undefined,
): HighlightSegments {
  const unmarked: HighlightSegments = { before: text, mark: "", after: "", valid: false };
  if (
    typeof charStart !== "number" ||
    typeof charEnd !== "number" ||
    !Number.isFinite(charStart) ||
    !Number.isFinite(charEnd)
  ) {
    return unmarked;
  }

  const units = ASTRAL.test(text) ? Array.from(text) : null;
  const length = units ? units.length : text.length;
  const start = clamp(Math.floor(charStart), 0, length);
  const end = clamp(Math.floor(charEnd), 0, length);
  if (end <= start) return unmarked;

  const slice = (from: number, to?: number) =>
    units ? units.slice(from, to).join("") : text.slice(from, to);

  return { before: slice(0, start), mark: slice(start, end), after: slice(end), valid: true };
}

export interface ActiveSpan {
  childId: string;
  charStart: number;
  charEnd: number;
  /** Server-provided highlight text, when the span came from `highlight` (used as a check). */
  expectedText: string | null;
}

interface SpanSource {
  children: ReadonlyArray<{ child_id: string; char_start: number; char_end: number }>;
  highlight: { child_id: string; char_start: number; char_end: number; text: string } | null;
}

/**
 * Picks the span to mark: the server highlight when it matches the requested child,
 * otherwise the requested child's offsets from `children`; null when nothing matches.
 */
export function resolveActiveSpan(evidence: SpanSource, childId: string | null): ActiveSpan | null {
  const hl = evidence.highlight;
  if (hl && (!childId || hl.child_id === childId)) {
    return { childId: hl.child_id, charStart: hl.char_start, charEnd: hl.char_end, expectedText: hl.text };
  }
  const child = childId ? evidence.children.find((c) => c.child_id === childId) : undefined;
  if (!child) return null;
  return { childId: child.child_id, charStart: child.char_start, charEnd: child.char_end, expectedText: null };
}
