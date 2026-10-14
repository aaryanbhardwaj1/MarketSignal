import { describe, expect, it } from "vitest";
import type { ServerLogEntry } from "@/lib/api/contracts";
import {
  DEFAULT_LOG_FILTERS,
  LOG_BUFFER_LIMIT,
  filterKey,
  filtersToParams,
  formatLogTime,
  hasActiveFilters,
  isAtBottom,
  levelLabel,
  levelTone,
  logDetailRows,
  logSubject,
  mergeLogEntries,
  methodTone,
  nextCursor,
  shortCorrelation,
  statusTone,
} from "./log-model";

function entry(seq: number, over: Partial<ServerLogEntry> = {}): ServerLogEntry {
  return {
    seq,
    ts: "2026-10-14T09:05:03.042Z",
    level: "INFO",
    logger: "marketsignal.api",
    event: "http.request",
    kind: "http",
    request_id: `req-${seq}-abcdef`,
    run_id: null,
    workspace: "NORTHSTAR",
    http: { method: "GET", route: "/api/workspaces/{ws}/runs", path: "/api/workspaces/NORTHSTAR/runs", status: 200, duration_ms: 12.5 },
    fields: {},
    ...over,
  };
}

describe("filtersToParams", () => {
  it("omits empty values and trims search", () => {
    expect(filtersToParams(DEFAULT_LOG_FILTERS)).toEqual({});
    expect(
      filtersToParams({ ...DEFAULT_LOG_FILTERS, level: "WARNING", kind: "http", method: "POST", status_class: "5xx", route: "/x", q: "  abc ", include_noise: true }),
    ).toEqual({ level: "WARNING", kind: "http", method: "POST", status_class: "5xx", route: "/x", q: "abc", include_noise: true });
    expect(filtersToParams({ ...DEFAULT_LOG_FILTERS, q: "   " })).toEqual({});
  });

  it("keys and active state follow the effective params", () => {
    expect(filterKey({ ...DEFAULT_LOG_FILTERS, q: " " })).toBe(filterKey(DEFAULT_LOG_FILTERS));
    expect(hasActiveFilters(DEFAULT_LOG_FILTERS)).toBe(false);
    expect(hasActiveFilters({ ...DEFAULT_LOG_FILTERS, include_noise: true })).toBe(true);
  });
});

describe("mergeLogEntries", () => {
  it("dedupes by seq and returns ascending order from either wire order", () => {
    const snapshot = [entry(5), entry(4), entry(3)]; // newest first
    const poll = [entry(5, { event: "dup" }), entry(6), entry(7)];
    const merged = mergeLogEntries(mergeLogEntries([], snapshot), poll);
    expect(merged.map((e) => e.seq)).toEqual([3, 4, 5, 6, 7]);
    expect(merged.find((e) => e.seq === 5)?.event).toBe("dup");
  });

  it("keeps only the newest entries within the cap", () => {
    const many = Array.from({ length: LOG_BUFFER_LIMIT + 50 }, (_, i) => entry(i + 1));
    const merged = mergeLogEntries([], many);
    expect(merged).toHaveLength(LOG_BUFFER_LIMIT);
    expect(merged[0].seq).toBe(51);
    expect(mergeLogEntries(merged, [entry(2000)], 3).map((e) => e.seq)).toEqual([LOG_BUFFER_LIMIT + 49, LOG_BUFFER_LIMIT + 50, 2000]);
  });
});

describe("nextCursor", () => {
  it("jumps to latest_seq when the page is not full", () => {
    expect(nextCursor(10, { entries: [entry(11)], latest_seq: 40 }, 500, true)).toBe(40);
    expect(nextCursor(null, { entries: [entry(9), entry(8)], latest_seq: 12 }, 200, false)).toBe(12);
  });

  it("resumes after the last entry of a full incremental page", () => {
    expect(nextCursor(10, { entries: [entry(11), entry(12)], latest_seq: 90 }, 2, true)).toBe(12);
  });

  it("never moves backwards and handles an empty buffer", () => {
    expect(nextCursor(50, { entries: [], latest_seq: 20 }, 500, true)).toBe(50);
    expect(nextCursor(null, { entries: [], latest_seq: null }, 500, true)).toBeNull();
  });
});

describe("display mapping", () => {
  it("formats HH:MM:SS.mmm", () => {
    expect(formatLogTime("2026-10-14T09:05:03.042Z", { utc: true })).toBe("09:05:03.042");
    expect(formatLogTime("nope")).toBe("-");
    const d = new Date("2026-10-14T23:59:59.999Z");
    expect(formatLogTime(d.toISOString())).toMatch(/^\d{2}:\d{2}:\d{2}\.999$/);
  });

  it("maps levels, statuses and methods to tones", () => {
    expect(levelTone("INFO")).toBe("neutral");
    expect(levelTone("DEBUG")).toBe("neutral");
    expect(levelTone("WARNING")).toBe("warn");
    expect(levelTone("ERROR")).toBe("danger");
    expect(levelTone("CRITICAL")).toBe("danger");
    expect(levelLabel("WARNING")).toBe("WARN");
    expect(statusTone(204)).toBe("success");
    expect(statusTone(304)).toBe("info");
    expect(statusTone(404)).toBe("warn");
    expect(statusTone(503)).toBe("danger");
    expect(statusTone(null)).toBe("neutral");
    expect(methodTone("get")).toBe("info");
    expect(methodTone("POST")).toBe("success");
    expect(methodTone("PATCH")).toBe("warn");
    expect(methodTone("DELETE")).toBe("danger");
    expect(methodTone("TRACE")).toBe("neutral");
    expect(methodTone(null)).toBe("neutral");
  });

  it("shows the route template, the raw path when unmatched, or the event", () => {
    expect(logSubject(entry(1))).toBe("/api/workspaces/{ws}/runs");
    expect(logSubject(entry(1, { http: { method: "GET", route: null, path: "/nope", status: 404, duration_ms: 1 } }))).toBe("/nope");
    expect(logSubject(entry(1, { http: null, kind: "run", event: "run.completed" }))).toBe("run.completed");
    expect(shortCorrelation("288b6e18-8682-4d67")).toBe("288b6e18");
    expect(shortCorrelation("abc")).toBe("abc");
  });

  it("lists only fields present in the entry, sorted", () => {
    const rows = logDetailRows(entry(3, { run_id: "r-1", fields: { zeta: 1, alpha: null, noise: true } }));
    const keys = rows.map((r) => r.key);
    expect(keys).toEqual(["seq", "ts", "event", "logger", "workspace", "request_id", "run_id", "http.path", "http.route", "alpha", "noise", "zeta"]);
    expect(rows.find((r) => r.key === "alpha")?.value).toBe("null");
    const bare = logDetailRows(entry(4, { logger: null, workspace: null, request_id: null, http: null }));
    expect(bare.map((r) => r.key)).toEqual(["seq", "ts", "event"]);
  });

  it("detects the bottom of the scroll area with slack", () => {
    expect(isAtBottom({ scrollHeight: 1000, scrollTop: 590, clientHeight: 400 })).toBe(true);
    expect(isAtBottom({ scrollHeight: 1000, scrollTop: 500, clientHeight: 400 })).toBe(false);
  });
});
