import { describe, expect, it } from "vitest";
import type { SourceSummary, VersionStatus } from "./api/types";
import {
  hasInFlightSources,
  isNonTerminalStatus,
  isTerminalStatus,
  retryable,
  statusTone,
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
    expect(isTerminalStatus(status)).toBe(false);
    expect(statusTone(status)).toBe("progress");
  });

  it.each(TERMINAL)("%s is terminal", (status) => {
    expect(isTerminalStatus(status)).toBe(true);
    expect(isNonTerminalStatus(status)).toBe(false);
  });

  it("treats unknown and missing statuses as neither", () => {
    expect(isTerminalStatus("weird")).toBe(false);
    expect(isNonTerminalStatus(undefined)).toBe(false);
    expect(statusTone("weird")).toBe("muted");
  });

  it("assigns distinct tones to terminal outcomes", () => {
    expect(statusTone("ready")).toBe("success");
    expect(statusTone("ready_degraded")).toBe("warning");
    expect(statusTone("failed")).toBe("danger");
    expect(statusTone("superseded")).toBe("muted");
  });

  it("only failed versions are retryable", () => {
    expect(retryable("failed")).toBe(true);
    expect(retryable("ready")).toBe(false);
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
