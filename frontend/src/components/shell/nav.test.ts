import { describe, expect, it } from "vitest";
import { NAV, NAV_ITEMS, activeNavId, isTestWorkspace, switchWorkspaceHref } from "./nav";
import {
  chatRedirectTarget,
  rootRedirectTarget,
  searchRedirectTarget,
  sourceDetailRedirectTarget,
  sourcesRedirectTarget,
  workspaceRootTarget,
} from "./routes";

describe("NAV", () => {
  it("has the two groups with the product labels, in order", () => {
    expect(NAV.map((g) => g.group)).toEqual(["Workspace", "Developer tools"]);
    expect(NAV[0].items.map((i) => i.label)).toEqual([
      "Overview",
      "Ask MarketSignal",
      "Growth Opportunities",
      "Analytics",
      "Evidence Library",
    ]);
    expect(NAV[1].items.map((i) => i.label)).toEqual(["Telemetry", "RAG Evaluation"]);
  });

  it("builds workspace-scoped hrefs", () => {
    const hrefs = Object.fromEntries(NAV_ITEMS.map((i) => [i.id, i.href("NORTHSTAR")]));
    expect(hrefs).toMatchObject({
      overview: "/w/NORTHSTAR/overview",
      ask: "/w/NORTHSTAR/ask",
      evidence: "/w/NORTHSTAR/evidence",
      telemetry: "/w/NORTHSTAR/dev/telemetry",
      evaluation: "/w/NORTHSTAR/dev/evaluation",
    });
  });
});

describe("activeNavId", () => {
  it.each([
    ["/w/NORTHSTAR/overview", "overview"],
    ["/w/NORTHSTAR/ask/3f2b7c9e", "ask"],
    ["/w/NORTHSTAR/evidence/sources/abc", "evidence"],
    ["/w/NORTHSTAR/dev/telemetry/runs/r1", "telemetry"],
    ["/w/NORTHSTAR/dev/evaluation", "evaluation"],
  ])("%s → %s", (path, id) => {
    expect(activeNavId(path, "NORTHSTAR")).toBe(id);
  });

  it("matches whole segments only and ignores other workspaces", () => {
    expect(activeNavId("/w/NORTHSTAR/asking", "NORTHSTAR")).toBeNull();
    expect(activeNavId("/w/SOUTHPEAK/overview", "NORTHSTAR")).toBeNull();
    expect(activeNavId("/w/NORTHSTAR", "NORTHSTAR")).toBeNull();
  });
});

describe("switchWorkspaceHref", () => {
  it("keeps the section but drops record ids", () => {
    expect(switchWorkspaceHref("/w/NORTHSTAR/ask/abc", "NORTHSTAR", "SOUTHPEAK")).toBe("/w/SOUTHPEAK/ask");
    expect(switchWorkspaceHref("/w/NORTHSTAR/dev/telemetry", "NORTHSTAR", "SOUTHPEAK")).toBe("/w/SOUTHPEAK/dev/telemetry");
  });

  it("falls back to the overview", () => {
    expect(switchWorkspaceHref("/w/NORTHSTAR", "NORTHSTAR", "SOUTHPEAK")).toBe("/w/SOUTHPEAK/overview");
  });
});

describe("isTestWorkspace", () => {
  it("matches only harness codes", () => {
    expect(isTestWorkspace("T0123456789")).toBe(true);
    expect(isTestWorkspace("TABCDEF0123")).toBe(true);
    expect(isTestWorkspace("NORTHSTAR")).toBe(false);
    expect(isTestWorkspace("T012345678")).toBe(false);
    expect(isTestWorkspace("TEAMSPACE01")).toBe(false);
  });
});

describe("redirect targets", () => {
  it("root prefers NORTHSTAR, then the first visible workspace", () => {
    expect(rootRedirectTarget([{ code: "T0123456789" }, { code: "SOUTHPEAK" }, { code: "NORTHSTAR" }])).toBe(
      "/w/NORTHSTAR/overview",
    );
    expect(rootRedirectTarget([{ code: "T0123456789" }, { code: "SOUTHPEAK" }])).toBe("/w/SOUTHPEAK/overview");
    expect(rootRedirectTarget([{ code: "T0123456789" }])).toBe("/w/NORTHSTAR/overview");
    expect(rootRedirectTarget(null)).toBe("/w/NORTHSTAR/overview");
  });

  it("maps /w/[ws] to the overview", () => {
    expect(workspaceRootTarget("NORTHSTAR")).toBe("/w/NORTHSTAR/overview");
  });

  it("maps legacy chat to ask", () => {
    expect(chatRedirectTarget("NORTHSTAR", "abc-123")).toBe("/w/NORTHSTAR/ask/abc-123");
    expect(chatRedirectTarget("NORTHSTAR", ["x/y", "z"])).toBe("/w/NORTHSTAR/ask/x%2Fy");
    expect(chatRedirectTarget("NORTHSTAR", undefined)).toBe("/w/NORTHSTAR/ask");
    expect(chatRedirectTarget("NORTHSTAR", "  ")).toBe("/w/NORTHSTAR/ask");
  });

  it("maps legacy sources and search to the Evidence Library", () => {
    expect(sourcesRedirectTarget("NORTHSTAR")).toBe("/w/NORTHSTAR/evidence");
    expect(sourceDetailRedirectTarget("NORTHSTAR", "abc")).toBe("/w/NORTHSTAR/evidence/sources/abc");
    expect(searchRedirectTarget("NORTHSTAR", "gen z & tiktok")).toBe("/w/NORTHSTAR/evidence?q=gen+z+%26+tiktok");
    expect(searchRedirectTarget("NORTHSTAR", undefined)).toBe("/w/NORTHSTAR/evidence");
  });
});
