import { describe, expect, it } from "vitest";
import {
  evidenceApiPath,
  evidenceViewerHref,
  handleAtVersion,
  isUuid,
  parseHandle,
  resultApiPath,
} from "./handles";

const HANDLES = ["NORTHSTAR/SURVEY-2026@v1:R185", "NORTHSTAR/Q3-REVIEW@v1:SL6.N1"];

describe("evidenceApiPath", () => {
  it.each(HANDLES)("encodes %s as a single path segment", (handle) => {
    const path = evidenceApiPath("NORTHSTAR", handle);
    const segment = path.split("/evidence/")[1];
    expect(segment).not.toContain("/");
    expect(segment).not.toContain("@");
    expect(segment).not.toContain(":");
    expect(decodeURIComponent(segment)).toBe(handle);
    expect(path.startsWith("/api/workspaces/NORTHSTAR/evidence/")).toBe(true);
  });

  it("produces the exact encoded form", () => {
    expect(evidenceApiPath("NORTHSTAR", "NORTHSTAR/SURVEY-2026@v1:R185")).toBe(
      "/api/workspaces/NORTHSTAR/evidence/NORTHSTAR%2FSURVEY-2026%40v1%3AR185",
    );
  });
});

describe("evidenceViewerHref", () => {
  it.each(HANDLES)("round-trips %s through search params", (handle) => {
    const child = "3ff78a09-fb48-4313-9856-c33f561913a0";
    const href = evidenceViewerHref("NORTHSTAR", handle, child);
    const url = new URL(href, "http://localhost:3000");
    expect(url.pathname).toBe("/w/NORTHSTAR/evidence");
    expect(url.searchParams.get("h")).toBe(handle);
    expect(url.searchParams.get("child")).toBe(child);
  });

  it("omits child when absent", () => {
    const url = new URL(evidenceViewerHref("NORTHSTAR", HANDLES[0]), "http://x");
    expect(url.searchParams.has("child")).toBe(false);
  });
});

describe("parseHandle / handleAtVersion", () => {
  it("parses canonical handles", () => {
    expect(parseHandle("NORTHSTAR/Q3-REVIEW@v1:SL6.N1")).toEqual({
      workspace: "NORTHSTAR",
      sourceCode: "Q3-REVIEW",
      version: 1,
      locator: "SL6.N1",
    });
    expect(parseHandle("garbage")).toBeNull();
    expect(parseHandle("NORTHSTAR/X@vA:P1")).toBeNull();
  });

  it("rewrites the version while keeping the locator", () => {
    expect(handleAtVersion("NORTHSTAR/GENZ-TRENDS@v1:P1.B1", 2)).toBe(
      "NORTHSTAR/GENZ-TRENDS@v2:P1.B1",
    );
    expect(handleAtVersion("garbage", 2)).toBeNull();
    expect(handleAtVersion("NORTHSTAR/X@v1:P1", 0)).toBeNull();
  });
});

describe("isUuid", () => {
  it("accepts UUIDs only", () => {
    expect(isUuid("3ff78a09-fb48-4313-9856-c33f561913a0")).toBe(true);
    expect(isUuid("notauuid")).toBe(false);
  });
});

describe("resultApiPath", () => {
  it("encodes workspace and result id as single segments", () => {
    expect(resultApiPath("NORTHSTAR", "3f2b7c9e-8a41-4d6b-b0a1-5c2d9e7f1a30")).toBe(
      "/api/workspaces/NORTHSTAR/results/3f2b7c9e-8a41-4d6b-b0a1-5c2d9e7f1a30",
    );
    expect(resultApiPath("A/B", "x/y")).toBe("/api/workspaces/A%2FB/results/x%2Fy");
  });
});
