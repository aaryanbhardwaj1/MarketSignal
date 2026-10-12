import { describe, expect, it } from "vitest";
import type { SourceDetail, SourceSummary, SourceVersion, VersionStatus } from "./api/types";
import {
  DEFAULT_LIBRARY_FILTERS,
  distinctValues,
  filterLibraryRows,
  filterSearchGroups,
  isFiltered,
  libraryCounts,
  mergeRows,
  parseLibraryFilters,
  sourceRows,
  sourcesWithHistory,
  supersededRows,
  versionHistory,
  versionLabel,
  writeLibraryFilters,
} from "./library-filters";

function version(n: number, status: VersionStatus, extra: Partial<SourceVersion> = {}): SourceVersion {
  return {
    version_id: `v${n}`,
    version: n,
    status,
    source_class: "market",
    confidentiality: "internal",
    original_filename: null,
    byte_size: null,
    error_code: null,
    error_detail: null,
    warnings: [],
    parent_count: 10 * n,
    child_count: 40 * n,
    embedding_model: null,
    timings: null,
    health: null,
    attempts: 1,
    created_at: `2026-0${n}-01T00:00:00Z`,
    ready_at: status === "ready" || status === "superseded" ? `2026-0${n}-02T00:00:00Z` : null,
    ...extra,
  };
}

function source(id: string, title: string, latest: SourceVersion | null, extra: Partial<SourceSummary> = {}): SourceSummary {
  return { source_id: id, source_code: id.toUpperCase(), title, source_type: "pdf", deleted: false, current_version_id: latest?.version_id ?? null, latest, ...extra };
}

const trends = source("trends", "Gen Z Trends", version(2, "ready"));
const survey = source("survey", "Customer Survey", version(1, "ready", { source_class: "customer" }), { source_type: "xlsx" });
const pending = source("pending", "Pending deck", version(1, "embedding"), { source_type: "pptx" });
const failed = source("failed", "Broken file", version(1, "failed"));
const removed = source("gone", "Removed source", version(1, "ready"), { deleted: true });
const all = [trends, survey, pending, failed, removed];

const trendsDetail: SourceDetail = {
  source_id: "trends",
  source_code: "TRENDS",
  title: "Gen Z Trends",
  source_type: "pdf",
  deleted: false,
  current_version_id: "v2",
  versions: [version(1, "superseded"), version(2, "ready")],
};

describe("sourceRows", () => {
  it("lists one current row per live source and drops removed sources", () => {
    const rows = sourceRows(all);
    expect(rows.map((r) => r.title)).toEqual(["Gen Z Trends", "Customer Survey", "Pending deck", "Broken file"]);
    expect(rows.every((r) => r.isCurrent)).toBe(true);
    expect(rows.find((r) => r.sourceId === "pending")?.bucket).toBe("processing");
  });

  it("treats a source with no version yet as processing", () => {
    const [row] = sourceRows([source("new", "New", null)]);
    expect(row).toMatchObject({ bucket: "processing", version: null, passages: null });
  });
});

describe("superseded versions", () => {
  it("only fetches history for sources with more than one version", () => {
    expect(sourcesWithHistory(all)).toEqual(["trends"]);
  });

  it("places superseded rows directly after their source, newest first", () => {
    const merged = mergeRows(sourceRows(all), supersededRows(trendsDetail));
    const idx = merged.findIndex((r) => r.sourceId === "trends" && r.isCurrent);
    expect(merged[idx + 1]).toMatchObject({ sourceId: "trends", version: 1, isCurrent: false, bucket: "superseded" });
  });
});

describe("filterLibraryRows", () => {
  const rows = mergeRows(sourceRows(all), supersededRows(trendsDetail));

  it("hides superseded rows unless included", () => {
    expect(filterLibraryRows(rows, DEFAULT_LIBRARY_FILTERS).some((r) => !r.isCurrent)).toBe(false);
    expect(filterLibraryRows(rows, { ...DEFAULT_LIBRARY_FILTERS, includeSuperseded: true }).some((r) => !r.isCurrent)).toBe(true);
  });

  it("filtering by the superseded status shows superseded rows without the toggle", () => {
    const shown = filterLibraryRows(rows, { ...DEFAULT_LIBRARY_FILTERS, status: "superseded" });
    expect(shown.map((r) => `${r.sourceId}:${r.version}`)).toEqual(["trends:1"]);
  });

  it("filters by type, category and status together", () => {
    expect(filterLibraryRows(rows, { ...DEFAULT_LIBRARY_FILTERS, type: "xlsx" }).map((r) => r.sourceId)).toEqual(["survey"]);
    expect(filterLibraryRows(rows, { ...DEFAULT_LIBRARY_FILTERS, cls: "customer" }).map((r) => r.sourceId)).toEqual(["survey"]);
    expect(filterLibraryRows(rows, { ...DEFAULT_LIBRARY_FILTERS, status: "failed" }).map((r) => r.sourceId)).toEqual(["failed"]);
    expect(filterLibraryRows(rows, { ...DEFAULT_LIBRARY_FILTERS, status: "processing", type: "pdf" })).toEqual([]);
  });

  it("lists distinct option values", () => {
    expect(distinctValues(rows, "sourceType")).toEqual(["pdf", "pptx", "xlsx"]);
    expect(distinctValues(rows, "sourceClass")).toEqual(["customer", "market"]);
  });
});

describe("URL round trip", () => {
  it("parses known values and ignores unknown statuses", () => {
    const params = new URLSearchParams("type=pdf&class=market&status=bogus&versions=all");
    expect(parseLibraryFilters(params)).toEqual({ type: "pdf", cls: "market", status: "", includeSuperseded: true });
  });

  it("writes filters while keeping search and drawer params", () => {
    const next = writeLibraryFilters("q=fit&ev=abc&type=pdf", { type: "", cls: "customer", status: "ready", includeSuperseded: false });
    expect(next.get("q")).toBe("fit");
    expect(next.get("ev")).toBe("abc");
    expect(next.has("type")).toBe(false);
    expect(next.get("class")).toBe("customer");
    expect(next.get("status")).toBe("ready");
    expect(next.has("versions")).toBe(false);
    expect(parseLibraryFilters(next)).toEqual({ type: "", cls: "customer", status: "ready", includeSuperseded: false });
  });

  it("reports whether any filter is active", () => {
    expect(isFiltered(DEFAULT_LIBRARY_FILTERS)).toBe(false);
    expect(isFiltered({ ...DEFAULT_LIBRARY_FILTERS, includeSuperseded: true })).toBe(true);
  });
});

describe("libraryCounts", () => {
  it("counts live sources and passages from ready versions only", () => {
    expect(libraryCounts(all)).toEqual({ sources: 4, ready: 2, processing: 1, failed: 1, passages: 30, segments: 120 });
  });
});

describe("version labels and history", () => {
  it("labels current and superseded versions", () => {
    expect(versionLabel({ version: 2, isCurrent: true, bucket: "ready" })).toBe("Version 2 · Current");
    expect(versionLabel({ version: 1, isCurrent: false, bucket: "superseded" })).toBe("Version 1 · Superseded");
    expect(versionLabel({ version: null, isCurrent: true, bucket: "processing" })).toBe("-");
  });

  it("orders history newest first and marks the current version", () => {
    const history = versionHistory(trendsDetail);
    expect(history.map((h) => [h.version, h.isCurrent, h.bucket])).toEqual([
      [2, true, "ready"],
      [1, false, "superseded"],
    ]);
    expect(history[0].date).toBe("2026-02-02T00:00:00Z");
  });

  it("marks nothing current on a removed source", () => {
    expect(versionHistory({ ...trendsDetail, deleted: true }).every((h) => !h.isCurrent && h.bucket === "removed")).toBe(true);
  });
});

describe("filterSearchGroups", () => {
  it("applies type and category filters to search groups", () => {
    const groups = [
      { sourceClass: "market", sourceType: "pdf", id: 1 },
      { sourceClass: "customer", sourceType: "xlsx", id: 2 },
    ];
    expect(filterSearchGroups(groups, { type: "", cls: "" }).map((g) => g.id)).toEqual([1, 2]);
    expect(filterSearchGroups(groups, { type: "xlsx", cls: "" }).map((g) => g.id)).toEqual([2]);
    expect(filterSearchGroups(groups, { type: "pdf", cls: "customer" })).toEqual([]);
  });
});
