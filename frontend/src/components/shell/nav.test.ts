import { describe, expect, it } from "vitest";
import { DEV_TOOLS, NAV_ITEMS, PRIMARY_NAV, activeNavId, isTestWorkspace, switchWorkspaceHref } from "./nav";
import {
  chatRedirectTarget,
  overviewRedirectTarget,
  rootRedirectTarget,
  searchRedirectTarget,
  sourceDetailRedirectTarget,
  sourcesRedirectTarget,
  workspaceRootTarget,
} from "./routes";

describe("navigation model", () => {
  it("primary nav is Chat · Insights · Growth Opportunities · Analytics", () => {
    expect(PRIMARY_NAV.map((i) => i.label)).toEqual(["Chat", "Insights", "Growth Opportunities", "Analytics"]);
    expect(PRIMARY_NAV.map((i) => i.href("NORTHSTAR"))).toEqual([
      "/w/NORTHSTAR/ask",
      "/w/NORTHSTAR/insights",
      "/w/NORTHSTAR/opportunities",
      "/w/NORTHSTAR/analytics",
    ]);
  });

  it("developer tools are Telemetry and RAG Evaluation", () => {
    expect(DEV_TOOLS.map((i) => [i.label, i.href("NORTHSTAR")])).toEqual([
      ["Telemetry", "/w/NORTHSTAR/dev/telemetry"],
      ["RAG Evaluation", "/w/NORTHSTAR/dev/evaluation"],
    ]);
  });

  it("knows the Evidence library as a section without a nav entry", () => {
    expect(NAV_ITEMS.find((i) => i.id === "evidence")?.href("NORTHSTAR")).toBe("/w/NORTHSTAR/evidence");
    expect(PRIMARY_NAV.some((i) => i.id === "evidence")).toBe(false);
  });
});

describe("activeNavId", () => {
  it.each([
    ["/w/NORTHSTAR/ask", "ask"],
    ["/w/NORTHSTAR/ask/3f2b7c9e", "ask"],
    ["/w/NORTHSTAR/insights", "insights"],
    ["/w/NORTHSTAR/insights/deck", "insights"],
    ["/w/NORTHSTAR/overview", "insights"],
    ["/w/NORTHSTAR/opportunities/o1", "opportunities"],
    ["/w/NORTHSTAR/analytics/a1", "analytics"],
    ["/w/NORTHSTAR/evidence/sources/abc", "evidence"],
    ["/w/NORTHSTAR/dev/telemetry/runs/r1", "telemetry"],
    ["/w/NORTHSTAR/dev/evaluation", "evaluation"],
    ["/w/NORTHSTAR/dev/evaluation?tab=retrieval", "evaluation"],
  ])("%s → %s", (path, id) => {
    expect(activeNavId(path, "NORTHSTAR")).toBe(id);
  });

  it("matches whole segments only and ignores other workspaces", () => {
    expect(activeNavId("/w/NORTHSTAR/asking", "NORTHSTAR")).toBeNull();
    expect(activeNavId("/w/NORTHSTAR/insightsx", "NORTHSTAR")).toBeNull();
    expect(activeNavId("/w/SOUTHPEAK/insights", "NORTHSTAR")).toBeNull();
    expect(activeNavId("/w/NORTHSTAR", "NORTHSTAR")).toBeNull();
    expect(activeNavId("/w/NORTHSTAR/dev", "NORTHSTAR")).toBeNull();
  });
});

describe("switchWorkspaceHref", () => {
  it("keeps the section but drops record ids", () => {
    expect(switchWorkspaceHref("/w/NORTHSTAR/ask/abc", "NORTHSTAR", "SOUTHPEAK")).toBe("/w/SOUTHPEAK/ask");
    expect(switchWorkspaceHref("/w/NORTHSTAR/insights", "NORTHSTAR", "SOUTHPEAK")).toBe("/w/SOUTHPEAK/insights");
    expect(switchWorkspaceHref("/w/NORTHSTAR/evidence/sources/s1", "NORTHSTAR", "SOUTHPEAK")).toBe("/w/SOUTHPEAK/evidence");
    expect(switchWorkspaceHref("/w/NORTHSTAR/dev/telemetry", "NORTHSTAR", "SOUTHPEAK")).toBe("/w/SOUTHPEAK/dev/telemetry");
  });

  it("falls back to Chat", () => {
    expect(switchWorkspaceHref("/w/NORTHSTAR", "NORTHSTAR", "SOUTHPEAK")).toBe("/w/SOUTHPEAK/ask");
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
  it("root opens Chat in NORTHSTAR, then the first visible workspace", () => {
    expect(rootRedirectTarget([{ code: "T0123456789" }, { code: "SOUTHPEAK" }, { code: "NORTHSTAR" }])).toBe("/w/NORTHSTAR/ask");
    expect(rootRedirectTarget([{ code: "T0123456789" }, { code: "SOUTHPEAK" }])).toBe("/w/SOUTHPEAK/ask");
    expect(rootRedirectTarget([{ code: "T0123456789" }])).toBe("/w/NORTHSTAR/ask");
    expect(rootRedirectTarget(null)).toBe("/w/NORTHSTAR/ask");
  });

  it("maps /w/[ws] to Chat and the old overview to Insights", () => {
    expect(workspaceRootTarget("NORTHSTAR")).toBe("/w/NORTHSTAR/ask");
    expect(overviewRedirectTarget("NORTHSTAR")).toBe("/w/NORTHSTAR/insights");
  });

  it("maps legacy chat to ask", () => {
    expect(chatRedirectTarget("NORTHSTAR", "abc-123")).toBe("/w/NORTHSTAR/ask/abc-123");
    expect(chatRedirectTarget("NORTHSTAR", ["x/y", "z"])).toBe("/w/NORTHSTAR/ask/x%2Fy");
    expect(chatRedirectTarget("NORTHSTAR", undefined)).toBe("/w/NORTHSTAR/ask");
    expect(chatRedirectTarget("NORTHSTAR", "  ")).toBe("/w/NORTHSTAR/ask");
  });

  it("maps legacy sources and search to the Evidence library", () => {
    expect(sourcesRedirectTarget("NORTHSTAR")).toBe("/w/NORTHSTAR/evidence");
    expect(sourceDetailRedirectTarget("NORTHSTAR", "abc")).toBe("/w/NORTHSTAR/evidence/sources/abc");
    expect(searchRedirectTarget("NORTHSTAR", "gen z & tiktok")).toBe("/w/NORTHSTAR/evidence?q=gen+z+%26+tiktok");
    expect(searchRedirectTarget("NORTHSTAR", undefined)).toBe("/w/NORTHSTAR/evidence");
  });
});
