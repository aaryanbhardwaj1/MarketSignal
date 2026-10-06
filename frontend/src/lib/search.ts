import {
  SEARCH_MODES,
  SOURCE_CLASSES,
  type SearchMode,
  type SearchParams,
  type SearchScores,
  type SourceClass,
} from "./api/types";

export const DEFAULT_SEARCH_MODE: SearchMode = "full";
export const DEFAULT_SEARCH_K = 10;

export const SEARCH_MODE_LABELS: Record<SearchMode, string> = {
  full: "Default (hybrid RRF)",
  hybrid: "Hybrid (RRF, no rerank)",
  dense: "Dense only",
  lexical: "Keyword only",
  rerank: "Hybrid + rerank (experimental)",
};

/** Unknown, missing or repeated-garbage values fall back to the default mode. */
export function parseSearchMode(value: string | null | undefined): SearchMode {
  return (SEARCH_MODES as readonly string[]).includes(value ?? "")
    ? (value as SearchMode)
    : DEFAULT_SEARCH_MODE;
}

/** Keeps only known source classes, de-duplicated, in canonical order. */
export function parseSourceClasses(value: string | string[] | undefined | null): SourceClass[] {
  const raw = Array.isArray(value) ? value : value ? [value] : [];
  return SOURCE_CLASSES.filter((c) => raw.includes(c));
}

const FLAG_MESSAGES: Record<string, string> = {
  RERANKER_UNAVAILABLE: "Reranker unavailable: showing fused order",
  RETRIEVAL_LEXICAL_FALLBACK: "Embedding model unavailable: keyword results only",
};

/** Human message for a response flag; unknown flags are shown verbatim. */
export function flagMessage(flag: string): string {
  return FLAG_MESSAGES[flag] ?? flag;
}

/** Query string for GET /search, with source_class / source repeated once per value. */
export function buildSearchQuery(params: SearchParams): string {
  const qs = new URLSearchParams();
  qs.set("q", params.q);
  qs.set("mode", params.mode);
  qs.set("k", String(params.k ?? DEFAULT_SEARCH_K));
  for (const c of params.sourceClasses ?? []) qs.append("source_class", c);
  for (const s of params.sources ?? []) qs.append("source", s);
  if (params.maxConfidentiality) qs.set("max_confidentiality", params.maxConfidentiality);
  return qs.toString();
}

/** In-app URL of the search page (q, mode, repeated source_class). */
export function searchHref(
  ws: string,
  q: string,
  mode: SearchMode,
  sourceClasses: readonly SourceClass[] = [],
): string {
  const qs = new URLSearchParams({ q, mode });
  for (const c of sourceClasses) qs.append("source_class", c);
  return `/w/${encodeURIComponent(ws)}/search?${qs.toString()}`;
}

/** Compact per-result stage line, e.g. `dense #3 · keyword #1 · fused #2 · rerank 0.87`. */
export function formatStageLine(scores: SearchScores): string {
  const parts: string[] = [];
  if (scores.lanes.dense !== undefined) parts.push(`dense #${scores.lanes.dense}`);
  if (scores.lanes.lexical !== undefined) parts.push(`keyword #${scores.lanes.lexical}`);
  parts.push(`fused #${scores.fused_rank}`);
  if (scores.rerank !== null && scores.rerank !== undefined && Number.isFinite(scores.rerank)) {
    parts.push(`rerank ${scores.rerank.toFixed(2)}`);
  }
  return parts.join(" · ");
}

function formatMs(ms: number): string {
  return Number.isFinite(ms) ? `${Math.round(ms * 10) / 10} ms` : String(ms);
}

/** Timings line with total first, then each stage with its `_ms` suffix dropped. */
export function formatTimings(timings: Record<string, number>): string {
  const entries = Object.entries(timings);
  const total = entries.find(([k]) => k === "total_ms");
  const stages = entries.filter(([k]) => k !== "total_ms");
  const parts: string[] = [];
  if (total) parts.push(`total ${formatMs(total[1])}`);
  for (const [key, value] of stages) parts.push(`${key.replace(/_ms$/, "")} ${formatMs(value)}`);
  return parts.join(" · ");
}
