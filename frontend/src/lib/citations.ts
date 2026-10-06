/**
 * Citation-marker parsing for answer text.
 *
 * Two marker families exist:
 * - `[E3]`: run-local aliases in streamed draft text. A chip is shown only once a `citation`
 *   event bound the alias; an unbound alias renders as nothing (never the raw marker).
 * - `[[WS/SOURCE@vN:LOCATOR]]`: canonical handles in final / stored text. A chip uses the matching
 *   card from `citations`; a handle without a card renders as an inert "unverified" chip.
 * `[inference]` tags are lifted out too so they can be shown as a label instead of raw text.
 *
 * Markers are swapped for private-use placeholders *before* Markdown parsing so that Markdown
 * syntax can never split or reinterpret a marker (e.g. `[E3](x)` as a link).
 */
import type { CitationCard } from "./api/types";
import type { AliasCitation } from "./run-stream";

export type ChipToken =
  | { kind: "alias"; alias: string; citation: AliasCitation }
  | { kind: "handle"; handle: string; card: CitationCard | null }
  | { kind: "inference" };

export type MarkerSegment = { kind: "text"; text: string } | ChipToken;

export interface CitationContext {
  aliases?: Readonly<Record<string, AliasCitation>>;
  cards?: readonly CitationCard[];
}

// [[HANDLE]] | [E#] | [inference] (whitespace/case tolerant, as the backend's INFERENCE_RE).
const MARKER_RE = /\[\[([^[\]\n]{1,120})\]\]|\[(E\d{1,4})\]|\[\s*inference\s*\]/gi;
const ALIAS_SHAPE = /^E\d{1,4}$/; // aliases are case-sensitive: `[e3]` is literal text
const INFERENCE_RE = /\s*\[\s*inference\s*\]/gi;

export const PLACEHOLDER_OPEN = "";
export const PLACEHOLDER_CLOSE = "";
const PLACEHOLDER_RE = /(\d+)/g;
const PRIVATE_MARKS_RE = /[]/g;

function resolveMarker(
  match: RegExpExecArray,
  ctx: CitationContext,
  cards: ReadonlyMap<string, CitationCard>,
): ChipToken | null | "literal" {
  const [, handle, alias] = match;
  if (handle !== undefined) {
    const trimmed = handle.trim();
    return { kind: "handle", handle: trimmed, card: cards.get(trimmed) ?? null };
  }
  if (alias !== undefined) {
    if (!ALIAS_SHAPE.test(alias)) return "literal";
    const citation = ctx.aliases?.[alias];
    return citation ? { kind: "alias", alias, citation } : null;
  }
  return { kind: "inference" };
}

/**
 * Splits text into plain-text and chip segments. Unknown aliases are dropped together with the
 * whitespace before them, so "growth [E9]." becomes "growth." rather than "growth .".
 */
export function tokenizeMarkers(text: string, ctx: CitationContext = {}): MarkerSegment[] {
  const cards = new Map((ctx.cards ?? []).map((c) => [c.handle, c] as const));
  const segments: MarkerSegment[] = [];
  let buffer = "";
  let last = 0;
  const re = new RegExp(MARKER_RE.source, MARKER_RE.flags);
  for (let match = re.exec(text); match; match = re.exec(text)) {
    buffer += text.slice(last, match.index);
    last = match.index + match[0].length;
    const token = resolveMarker(match, ctx, cards);
    if (token === "literal") {
      buffer += match[0];
    } else if (token === null) {
      buffer = buffer.replace(/[ \t]+$/, "");
    } else {
      if (buffer) segments.push({ kind: "text", text: buffer });
      buffer = "";
      segments.push(token);
    }
  }
  buffer += text.slice(last);
  if (buffer) segments.push({ kind: "text", text: buffer });
  return segments;
}

export interface PreparedMarkdown {
  /** Markdown source with every marker replaced by `{index}` (or removed). */
  source: string;
  tokens: ChipToken[];
}

/** Replaces markers with placeholders that Markdown treats as plain text. */
export function prepareMarkdown(text: string, ctx: CitationContext = {}): PreparedMarkdown {
  const tokens: ChipToken[] = [];
  let source = "";
  for (const segment of tokenizeMarkers(text.replace(PRIVATE_MARKS_RE, ""), ctx)) {
    if (segment.kind === "text") {
      source += segment.text;
    } else {
      source += `${PLACEHOLDER_OPEN}${tokens.length}${PLACEHOLDER_CLOSE}`;
      tokens.push(segment);
    }
  }
  return { source, tokens };
}

export type PlaceholderPart = { kind: "text"; text: string } | { kind: "chip"; index: number };

/** Splits a rendered text node back into text and placeholder indices. */
export function splitPlaceholders(text: string): PlaceholderPart[] {
  const parts: PlaceholderPart[] = [];
  let last = 0;
  for (const match of text.matchAll(PLACEHOLDER_RE)) {
    const start = match.index ?? 0;
    if (start > last) parts.push({ kind: "text", text: text.slice(last, start) });
    parts.push({ kind: "chip", index: Number(match[1]) });
    last = start + match[0].length;
  }
  if (last < text.length) parts.push({ kind: "text", text: text.slice(last) });
  return parts;
}

export interface UnitInference {
  text: string;
  inferred: boolean;
}

/** Removes `[inference]` tags from an answer unit and reports whether it carried one. */
export function stripInference(unit: string): UnitInference {
  const inferred = new RegExp(INFERENCE_RE.source, "i").test(unit);
  if (!inferred) return { text: unit, inferred: false };
  // The backend puts the tag before terminal punctuation ("x [inference]."), so dropping it
  // together with its leading whitespace leaves "x.".
  return { text: unit.replace(INFERENCE_RE, "").trim(), inferred: true };
}
