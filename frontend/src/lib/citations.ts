/**
 * Citation-marker parsing for answer text.
 *
 * Two marker families exist:
 * - `[E3]`: run-local aliases in streamed draft text. A chip is shown only once a `citation`
 *   event bound the alias; an unbound alias renders as nothing (never the raw marker).
 * - `[R2]` / `[[result:<uuid>]]`: computed (analytics) results, a distinct chip kind. `[R#]` is
 *   bound only by a `citation` event of kind "result"; `[[result:<uuid>]]` needs a UUID (the
 *   lowercase prefix never matches an evidence handle) and uses its card when one exists.
 * - `[[WS/SOURCE@vN:LOCATOR]]`: canonical handles in final / stored text. A chip uses the matching
 *   card from `citations`; a handle without a card renders as an inert "unverified" chip.
 * `[inference]` tags are lifted out too so they can be shown as a label instead of raw text.
 *
 * Markers are swapped for private-use placeholders *before* Markdown parsing so that Markdown
 * syntax can never split or reinterpret a marker (e.g. `[E3](x)` as a link).
 */
import { isResultCard, type AnyCitationCard, type CitationCard, type ResultCitationCard } from "./api/types";
import { isUuid } from "./handles";
import type { AliasCitation, AnyAliasCitation, ResultAliasCitation } from "./run-stream";

/** What a result chip knows without fetching: the card / alias summary, or null if none. */
export type ResultRef = ResultCitationCard | ResultAliasCitation;

export type ChipToken =
  | { kind: "alias"; alias: string; citation: AliasCitation }
  | { kind: "result"; resultId: string; ref: ResultRef | null }
  | { kind: "handle"; handle: string; card: CitationCard | null }
  | { kind: "inference" };

export type MarkerSegment = { kind: "text"; text: string } | ChipToken;

export interface CitationContext {
  aliases?: Readonly<Record<string, AnyAliasCitation>>;
  cards?: readonly AnyCitationCard[];
}

// [[HANDLE]] | [E#] | [R#] | [inference] (whitespace/case tolerant, as the backend's INFERENCE_RE).
const MARKER_RE = /\[\[([^[\]\n]{1,120})\]\]|\[([ER]\d{1,4})\]|\[\s*inference\s*\]/gi;
const ALIAS_SHAPE = /^[ER]\d{1,4}$/; // aliases are case-sensitive: `[e3]` is literal text
const RESULT_PREFIX = "result:";
const INFERENCE_RE = /\s*\[\s*inference\s*\]/gi;

export const PLACEHOLDER_OPEN = "";
export const PLACEHOLDER_CLOSE = "";
const PLACEHOLDER_RE = /(\d+)/g;
const PRIVATE_MARKS_RE = /[]/g;

interface CardIndex {
  evidence: ReadonlyMap<string, CitationCard>;
  results: ReadonlyMap<string, ResultCitationCard>;
}

function indexCards(cards: readonly AnyCitationCard[]): CardIndex {
  const evidence = new Map<string, CitationCard>();
  const results = new Map<string, ResultCitationCard>();
  for (const card of cards) {
    if (isResultCard(card)) results.set(card.result_id, card);
    else evidence.set(card.handle, card);
  }
  return { evidence, results };
}

function resolveResultHandle(handle: string, index: CardIndex): ChipToken | null {
  if (!handle.startsWith(RESULT_PREFIX)) return null;
  const resultId = handle.slice(RESULT_PREFIX.length).toLowerCase();
  if (!isUuid(resultId)) return null;
  return { kind: "result", resultId, ref: index.results.get(resultId) ?? null };
}

function resolveAlias(alias: string, ctx: CitationContext): ChipToken | null {
  const citation = ctx.aliases?.[alias];
  if (!citation) return null;
  const isResult = "kind" in citation && citation.kind === "result";
  // `[E#]` only ever resolves to evidence and `[R#]` only to a result: a mismatched binding is
  // treated as unannounced so the two families can never be confused.
  if (alias.startsWith("R")) {
    return isResult ? { kind: "result", resultId: citation.result_id, ref: citation } : null;
  }
  return isResult ? null : { kind: "alias", alias, citation: citation as AliasCitation };
}

function resolveMarker(
  match: RegExpExecArray,
  ctx: CitationContext,
  index: CardIndex,
): ChipToken | null | "literal" {
  const [, handle, alias] = match;
  if (handle !== undefined) {
    const trimmed = handle.trim();
    return (
      resolveResultHandle(trimmed, index) ?? {
        kind: "handle",
        handle: trimmed,
        card: index.evidence.get(trimmed) ?? null,
      }
    );
  }
  if (alias !== undefined) {
    if (!ALIAS_SHAPE.test(alias)) return "literal";
    return resolveAlias(alias, ctx);
  }
  return { kind: "inference" };
}

/**
 * Splits text into plain-text and chip segments. Unknown aliases are dropped together with the
 * whitespace before them, so "growth [E9]." becomes "growth." rather than "growth .".
 */
export function tokenizeMarkers(text: string, ctx: CitationContext = {}): MarkerSegment[] {
  const index = indexCards(ctx.cards ?? []);
  const segments: MarkerSegment[] = [];
  let buffer = "";
  let last = 0;
  const re = new RegExp(MARKER_RE.source, MARKER_RE.flags);
  for (let match = re.exec(text); match; match = re.exec(text)) {
    buffer += text.slice(last, match.index);
    last = match.index + match[0].length;
    const token = resolveMarker(match, ctx, index);
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
