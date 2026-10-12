/**
 * Evidence Library search helpers. Business pages never show retrieval modes, scores, timings or
 * raw flag codes, so only the query builder and the by-source grouping live here.
 */
import { type SearchMode, type SearchParams, type SearchItem } from "./api/types";

export const DEFAULT_SEARCH_MODE: SearchMode = "full";
const DEFAULT_SEARCH_K = 10;

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

export interface SearchGroup {
  sourceCode: string;
  title: string;
  sourceClass: string;
  sourceType: string;
  items: SearchItem[];
}

/**
 * Groups ranked results by source, keeping the order in which each source first appears and the
 * rank order inside each group. Scores are dropped from the business view entirely.
 */
export function groupSearchResults(items: readonly SearchItem[]): SearchGroup[] {
  const groups = new Map<string, SearchGroup>();
  for (const item of [...items].sort((a, b) => a.rank - b.rank)) {
    const existing = groups.get(item.source_code);
    if (existing) {
      existing.items.push(item);
    } else {
      groups.set(item.source_code, {
        sourceCode: item.source_code,
        title: item.source_title,
        sourceClass: item.source_class,
        sourceType: item.source_type,
        items: [item],
      });
    }
  }
  return [...groups.values()];
}
