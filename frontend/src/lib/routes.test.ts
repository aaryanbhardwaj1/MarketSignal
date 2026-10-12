import { describe, expect, it } from "vitest";
import {
  analysisHref,
  analyticsHref,
  askHref,
  evaluationHref,
  evidenceLibraryHref,
  opportunitiesHref,
  opportunityHref,
  overviewHref,
  sourceHref,
  telemetryHref,
  telemetryRunHref,
  workspaceHref,
} from "./routes";

describe("route builders", () => {
  it("build every workspace route", () => {
    expect(workspaceHref("NORTHSTAR")).toBe("/w/NORTHSTAR");
    expect(overviewHref("NORTHSTAR")).toBe("/w/NORTHSTAR/overview");
    expect(askHref("NORTHSTAR")).toBe("/w/NORTHSTAR/ask");
    expect(askHref("NORTHSTAR", null)).toBe("/w/NORTHSTAR/ask");
    expect(askHref("NORTHSTAR", "c1")).toBe("/w/NORTHSTAR/ask/c1");
    expect(opportunitiesHref("NORTHSTAR")).toBe("/w/NORTHSTAR/opportunities");
    expect(opportunityHref("NORTHSTAR", "o1")).toBe("/w/NORTHSTAR/opportunities/o1");
    expect(analyticsHref("NORTHSTAR")).toBe("/w/NORTHSTAR/analytics");
    expect(analyticsHref("NORTHSTAR", "datasets")).toBe("/w/NORTHSTAR/analytics#datasets");
    expect(analysisHref("NORTHSTAR", "a1")).toBe("/w/NORTHSTAR/analytics/a1");
    expect(evidenceLibraryHref("NORTHSTAR")).toBe("/w/NORTHSTAR/evidence");
    expect(evidenceLibraryHref("NORTHSTAR", { ev: "H/1@v1:x" })).toBe("/w/NORTHSTAR/evidence?ev=H%2F1%40v1%3Ax");
    expect(sourceHref("NORTHSTAR", "s1")).toBe("/w/NORTHSTAR/evidence/sources/s1");
    expect(telemetryHref("NORTHSTAR")).toBe("/w/NORTHSTAR/dev/telemetry");
    expect(telemetryRunHref("NORTHSTAR", "r1")).toBe("/w/NORTHSTAR/dev/telemetry/runs/r1");
    expect(evaluationHref("NORTHSTAR")).toBe("/w/NORTHSTAR/dev/evaluation");
  });

  it("URL-encode workspace codes and ids", () => {
    expect(askHref("A B", "x/y")).toBe("/w/A%20B/ask/x%2Fy");
    expect(sourceHref("WS", "a?b")).toBe("/w/WS/evidence/sources/a%3Fb");
  });
});
