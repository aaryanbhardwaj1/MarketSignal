/**
 * Evidence Library table model and filters. Pure functions over `GET /sources` (latest version per
 * source) and, when superseded versions are included, `GET /sources/{id}` version histories.
 * Filters are client-side and mirrored in the URL (`type`, `class`, `status`, `versions=all`).
 */
import type { SourceDetail, SourceSummary, SourceVersion } from "./api/types";
import { LIBRARY_STATUSES, isNonTerminalStatus, libraryStatus, type LibraryStatus } from "./status";

export interface LibraryRow {
  key: string;
  sourceId: string;
  title: string;
  sourceClass: string;
  sourceType: string;
  status: string | null;
  bucket: LibraryStatus;
  version: number | null;
  isCurrent: boolean;
  updatedAt: string | null;
  passages: number | null;
  segments: number | null;
}

export interface LibraryFilters {
  type: string; // "" = any
  cls: string; // "" = any
  status: LibraryStatus | ""; // "" = any
  includeSuperseded: boolean;
}

export const DEFAULT_LIBRARY_FILTERS: LibraryFilters = { type: "", cls: "", status: "", includeSuperseded: false };

interface ReadableParams {
  get(name: string): string | null;
}

function versionRow(source: Pick<SourceSummary, "source_id" | "title" | "source_type" | "deleted">, v: SourceVersion, isCurrent: boolean): LibraryRow {
  return {
    key: `${source.source_id}:${v.version}`,
    sourceId: source.source_id,
    title: source.title,
    sourceClass: v.source_class,
    sourceType: source.source_type,
    status: v.status,
    bucket: libraryStatus(v.status, source.deleted),
    version: v.version,
    isCurrent,
    updatedAt: v.ready_at ?? v.created_at,
    passages: v.parent_count,
    segments: v.child_count,
  };
}

/** One row per live source (its latest version). Removed sources are left out. */
export function sourceRows(sources: readonly SourceSummary[]): LibraryRow[] {
  return sources
    .filter((s) => !s.deleted)
    .map((s) =>
      s.latest
        ? versionRow(s, s.latest, true)
        : {
            key: `${s.source_id}:none`,
            sourceId: s.source_id,
            title: s.title,
            sourceClass: "",
            sourceType: s.source_type,
            status: null,
            bucket: "processing" as const,
            version: null,
            isCurrent: true,
            updatedAt: null,
            passages: null,
            segments: null,
          },
    );
}

/** Rows for the superseded versions in one source's history. */
export function supersededRows(detail: SourceDetail): LibraryRow[] {
  return detail.versions
    .filter((v) => v.status === "superseded")
    .map((v) => versionRow(detail, v, false));
}

/** Sources with more than one version: only these can have superseded history to fetch. */
export function sourcesWithHistory(sources: readonly SourceSummary[]): string[] {
  return sources.filter((s) => !s.deleted && (s.latest?.version ?? 0) > 1).map((s) => s.source_id);
}

/** Current rows plus superseded rows, each superseded row placed right after its source. */
export function mergeRows(current: readonly LibraryRow[], superseded: readonly LibraryRow[]): LibraryRow[] {
  const bySource = new Map<string, LibraryRow[]>();
  for (const row of superseded) bySource.set(row.sourceId, [...(bySource.get(row.sourceId) ?? []), row]);
  return [...current]
    .sort((a, b) => a.title.localeCompare(b.title))
    .flatMap((row) => [row, ...(bySource.get(row.sourceId) ?? []).sort((a, b) => (b.version ?? 0) - (a.version ?? 0))]);
}

export function filterLibraryRows(rows: readonly LibraryRow[], filters: LibraryFilters): LibraryRow[] {
  const showSuperseded = filters.includeSuperseded || filters.status === "superseded";
  return rows.filter(
    (row) =>
      (showSuperseded || row.isCurrent) &&
      (!filters.type || row.sourceType === filters.type) &&
      (!filters.cls || row.sourceClass === filters.cls) &&
      (!filters.status || row.bucket === filters.status),
  );
}

export function parseLibraryFilters(params: ReadableParams): LibraryFilters {
  const status = params.get("status") ?? "";
  return {
    type: params.get("type") ?? "",
    cls: params.get("class") ?? "",
    status: (LIBRARY_STATUSES as readonly string[]).includes(status) ? (status as LibraryStatus) : "",
    includeSuperseded: params.get("versions") === "all",
  };
}

/** Writes the filters into a copy of `current`, keeping unrelated params (q, ev, child, res). */
export function writeLibraryFilters(current: string | URLSearchParams, filters: LibraryFilters): URLSearchParams {
  const next = new URLSearchParams(current);
  const set = (name: string, value: string) => (value ? next.set(name, value) : next.delete(name));
  set("type", filters.type);
  set("class", filters.cls);
  set("status", filters.status);
  set("versions", filters.includeSuperseded ? "all" : "");
  return next;
}

export function isFiltered(filters: LibraryFilters): boolean {
  return Boolean(filters.type || filters.cls || filters.status || filters.includeSuperseded);
}

/** Distinct non-empty values of one row field, sorted. */
export function distinctValues(rows: readonly LibraryRow[], field: "sourceType" | "sourceClass"): string[] {
  return [...new Set(rows.map((r) => r[field]).filter(Boolean))].sort();
}

export interface LibraryCounts {
  sources: number;
  ready: number;
  processing: number;
  failed: number;
  passages: number;
  segments: number;
}

/** Header counts over live sources' latest versions. Passage counts include only ready versions. */
export function libraryCounts(sources: readonly SourceSummary[]): LibraryCounts {
  const live = sources.filter((s) => !s.deleted);
  const counts: LibraryCounts = { sources: live.length, ready: 0, processing: 0, failed: 0, passages: 0, segments: 0 };
  return live.reduce((acc, s) => {
    const bucket = libraryStatus(s.latest?.status ?? null);
    const ready = bucket === "ready";
    return {
      ...acc,
      ready: acc.ready + (ready ? 1 : 0),
      processing: acc.processing + (!s.latest || isNonTerminalStatus(s.latest.status) ? 1 : 0),
      failed: acc.failed + (bucket === "failed" && s.latest ? 1 : 0),
      passages: acc.passages + (ready ? (s.latest?.parent_count ?? 0) : 0),
      segments: acc.segments + (ready ? (s.latest?.child_count ?? 0) : 0),
    };
  }, counts);
}

/** Version cell text: "Version 2 · Current", "Version 1 · Superseded", or "-" while the first version is pending. */
export function versionLabel(row: Pick<LibraryRow, "version" | "isCurrent" | "bucket">): string {
  if (row.version == null) return "-";
  if (row.bucket === "superseded" || !row.isCurrent) return `Version ${row.version} · Superseded`;
  return `Version ${row.version} · Current`;
}

export interface VersionHistoryEntry {
  version: number;
  isCurrent: boolean;
  bucket: LibraryStatus;
  /** Date the version became ready, else when it was added. */
  date: string | null;
  passages: number | null;
  segments: number | null;
}

/** Newest-first version history; "current" is the version the source points at (or the newest live one). */
export function versionHistory(detail: Pick<SourceDetail, "versions" | "current_version_id" | "deleted">): VersionHistoryEntry[] {
  const sorted = [...detail.versions].sort((a, b) => b.version - a.version);
  const currentId =
    detail.current_version_id ?? sorted.find((v) => libraryStatus(v.status) !== "superseded")?.version_id ?? null;
  return sorted.map((v) => ({
    version: v.version,
    isCurrent: !detail.deleted && v.version_id === currentId,
    bucket: libraryStatus(v.status, detail.deleted),
    date: v.ready_at ?? v.created_at,
    passages: v.parent_count,
    segments: v.child_count,
  }));
}

interface SearchGroupLike {
  sourceClass: string;
  sourceType: string;
}

/** Applies the library's type and category filters to grouped search results. */
export function filterSearchGroups<G extends SearchGroupLike>(groups: readonly G[], filters: Pick<LibraryFilters, "type" | "cls">): G[] {
  return groups.filter((g) => (!filters.type || g.sourceType === filters.type) && (!filters.cls || g.sourceClass === filters.cls));
}
