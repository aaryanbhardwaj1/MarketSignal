import { describe, expect, it } from "vitest";
import type { SourceSummary, VersionStatus } from "./api/types";
import {
  hasInFlightSources,
  isNonTerminalStatus,
  libraryStatus,
  libraryStatusLabel,
  versionStatusLabel,
} from "./status";

const NON_TERMINAL: VersionStatus[] = ["queued", "parsing", "chunking", "embedding", "indexing"];
const TERMINAL: VersionStatus[] = ["ready", "ready_degraded", "failed", "superseded", "purged"];

function source(status: VersionStatus | null, deleted = false): SourceSummary {
  return {
    source_id: "id",
    source_code: "X",
    title: "x",
    source_type: "pdf",
    deleted,
    current_version_id: null,
    latest: status ? ({ status } as SourceSummary["latest"]) : null,
  };
}

describe("status classification", () => {
  it.each(NON_TERMINAL)("%s is non-terminal", (status) => {
    expect(isNonTerminalStatus(status)).toBe(true);
  });

  it.each(TERMINAL)("%s is terminal", (status) => {
    expect(isNonTerminalStatus(status)).toBe(false);
  });

  it("treats unknown and missing statuses as not in flight", () => {
    expect(isNonTerminalStatus("weird")).toBe(false);
    expect(isNonTerminalStatus(undefined)).toBe(false);
  });
});

describe("hasInFlightSources", () => {
  it("is true only when a live source is mid-pipeline", () => {
    expect(hasInFlightSources(undefined)).toBe(false);
    expect(hasInFlightSources([source("ready"), source("failed")])).toBe(false);
    expect(hasInFlightSources([source("ready"), source("embedding")])).toBe(true);
    expect(hasInFlightSources([source("queued", true)])).toBe(false);
    expect(hasInFlightSources([source(null)])).toBe(false);
  });
});

describe("library status buckets", () => {
  it("collapses pipeline stages into plain buckets", () => {
    for (const status of NON_TERMINAL) expect(libraryStatus(status)).toBe("processing");
    expect(libraryStatus("ready")).toBe("ready");
    expect(libraryStatus("ready_degraded")).toBe("ready");
    expect(libraryStatus("failed")).toBe("failed");
    expect(libraryStatus("superseded")).toBe("superseded");
    expect(libraryStatus("purged")).toBe("removed");
    expect(libraryStatus("ready", true)).toBe("removed");
  });

  it("labels buckets in business words with a tone", () => {
    expect(libraryStatusLabel("processing")).toEqual({ label: "Processing", tone: "info" });
    expect(versionStatusLabel("ready_degraded")).toEqual({ label: "Ready with warnings", tone: "warn" });
    expect(versionStatusLabel("superseded").label).toBe("Superseded");
  });
});
