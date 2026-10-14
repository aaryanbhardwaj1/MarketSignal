import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalysesResponse, InsightsBrief } from "../contracts";
import analyses from "../__fixtures__/insights-analyses.json";
import brief from "../__fixtures__/insights-brief.json";
import { getAnalyses, getAnalysis, getInsights, insightsKeys } from "./insights";

// JSON imports widen literal unions, so the captured payloads are cast to the contract types.
const typedBrief: InsightsBrief = brief as InsightsBrief;
const typedAnalyses: AnalysesResponse = analyses as AnalysesResponse;

function stubFetch(body: unknown, status = 200): ReturnType<typeof vi.fn> {
  const fetch = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const calledPath = (fetch: ReturnType<typeof vi.fn>): string =>
  new URL(String(fetch.mock.calls[0]?.[0])).pathname;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("insights getters", () => {
  it("fetches the curated brief for the workspace", async () => {
    const fetch = stubFetch(typedBrief);
    await expect(getInsights("NORTHSTAR")).resolves.toEqual(brief);
    expect(calledPath(fetch)).toBe("/api/workspaces/NORTHSTAR/insights");
  });

  it("fetches the named analyses and encodes an analysis id", async () => {
    const fetch = stubFetch(typedAnalyses);
    await getAnalyses("NORTHSTAR");
    expect(calledPath(fetch)).toBe("/api/workspaces/NORTHSTAR/analytics/analyses");
    const one = typedAnalyses.analyses[0];
    const fetchOne = stubFetch(one);
    await getAnalysis("NORTHSTAR", "a/b");
    expect(calledPath(fetchOne)).toBe("/api/workspaces/NORTHSTAR/analytics/analyses/a%2Fb");
  });

  it("surfaces ANALYSIS_NOT_FOUND as an error", async () => {
    stubFetch({ error: { code: "ANALYSIS_NOT_FOUND", message: "analysis not found" } }, 404);
    await expect(getAnalysis("NORTHSTAR", "nope")).rejects.toMatchObject({ status: 404 });
  });

  it("keys analyses under the workspace analytics namespace", () => {
    expect(insightsKeys.analysis("NORTHSTAR", "x")).toEqual([
      "workspace",
      "NORTHSTAR",
      "analytics",
      "analyses",
      "x",
    ]);
  });
});

describe("captured NORTHSTAR brief", () => {
  it("is fully verified with the planned shape", () => {
    expect(typedBrief.fixture_version).toBe("NORTHSTAR.v2");
    expect(typedBrief.corpus_check.status).toBe("ok");
    expect(typedBrief.signals).toHaveLength(21);
    expect(typedBrief.opportunities.map((o) => o.id)).toEqual(["O1", "O2", "O3", "O4"]);
    const items = [...typedBrief.signals, ...typedBrief.opportunities];
    expect(items.every((i) => i.integrity === "verified")).toBe(true);
    const refs = [
      ...typedBrief.signals.flatMap((s) => s.evidence),
      ...typedBrief.opportunities.flatMap((o) => [...o.supporting, ...o.contradicting]),
      ...typedBrief.opportunities.flatMap((o) => o.risks.flatMap((r) => r.evidence)),
    ];
    expect(refs.every((r) => r.integrity === "verified" && r.quote && r.char_start !== null)).toBe(true);
  });

  it("has every named analysis computed with provenance", () => {
    expect(typedAnalyses.analyses.length).toBeGreaterThanOrEqual(6);
    for (const a of typedAnalyses.analyses) {
      expect(a.status).toBe("computed");
      expect(a.rows.length).toBeGreaterThan(0);
      expect(a.provenance.rows_matched).not.toBeNull();
      expect(a.summary_status).toBe("verified");
    }
  });
});
