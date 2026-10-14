import { describe, expect, it } from "vitest";
import analysesFixture from "@/lib/api/__fixtures__/insights-analyses.json";
import briefFixture from "@/lib/api/__fixtures__/insights-brief.json";
import overviewFixture from "@/lib/api/__fixtures__/core-workspace-overview.json";
import type { AnalysesResponse, Analysis, EvidenceRef, InsightsBrief, MetricRef, WorkspaceOverview } from "@/lib/api/contracts";
import {
  describeBasis,
  buildMetricView,
  classBreakdown,
  drawerTarget,
  evidenceBalance,
  evidenceView,
  indexAnalyses,
  inputsComputed,
  metricViews,
  resolveDenominator,
  rowsMatchedText,
  sourceTotal,
  splitWorkspaceName,
  topMetric,
} from "./insights-view";

const brief = briefFixture as unknown as InsightsBrief;
const analyses = (analysesFixture as unknown as AnalysesResponse).analyses;
const index = indexAnalyses(analyses);
const overview = overviewFixture as unknown as WorkspaceOverview;

const signal = (id: string) => brief.signals.find((s) => s.id === id)!;
const opportunity = (id: string) => brief.opportunities.find((o) => o.id === id)!;
const analysis = (id: string) => analyses.find((a) => a.id === id)!;

describe("splitWorkspaceName", () => {
  it("splits client and engagement on ' - '", () => {
    expect(splitWorkspaceName("Northstar Athletics - Gen Z Growth Engagement")).toEqual({
      client: "Northstar Athletics",
      engagement: "Gen Z Growth Engagement",
    });
  });
  it("keeps the whole name when there is no engagement part", () => {
    expect(splitWorkspaceName("Southpeak Outdoor")).toEqual({ client: "Southpeak Outdoor", engagement: null });
  });
});

describe("workspace summary", () => {
  it("totals sources and orders the class breakdown customer first", () => {
    expect(sourceTotal(overview)).toBe(23);
    const breakdown = classBreakdown(overview);
    expect(breakdown[0]).toEqual({ code: "customer", label: "Customer research", count: 6 });
    expect(breakdown.map((c) => c.code)).toEqual(["customer", "market", "competitor", "internal", "financial"]);
  });
  it("drops empty classes", () => {
    expect(classBreakdown({ sources_by_class: { customer: 0, market: 2 } }).map((c) => c.code)).toEqual(["market"]);
  });
});

describe("metric denominators", () => {
  it("takes the per-row base of a multi-part analysis by matching the recomputed row", () => {
    const m = signal("fit-friction").metrics[0];
    expect(resolveDenominator(m, analysis(m.analysis_id))).toBe(400);
    expect(buildMetricView(m, index).basis).toBe("of 400 Gen Z respondents");
  });
  it("uses the analysis-wide base when present and says 'of' for record counts", () => {
    const m = opportunity("O4").metrics[0];
    const view = buildMetricView(m, index);
    expect(view.denominator).toBe(400);
    expect(view.basis).toBe("of 400 Gen Z respondents surveyed");
  });
  it("says 'across' for summed quantities", () => {
    const m = opportunity("O1").metrics[1]; // Q3 returns, fit runs large (a sum of return counts)
    expect(buildMetricView(m, index).basis).toBe("Total across 30 return records");
    expect(buildMetricView(m, index).baseLabel).toBe("Summed across");
  });
  it("gives a derived difference the shared base of its inputs", () => {
    const nps = signal("genz-nps-gap").metrics[0];
    expect(resolveDenominator(nps, analysis("nps-by-cohort"))).toBe(400);
  });
  it("never invents a base for a percent change", () => {
    const growth = signal("social-discovery").metrics[0];
    expect(resolveDenominator(growth, analysis("social-shop-sales-by-quarter"))).toBeNull();
    expect(buildMetricView(growth, index).basis).toBe("Based on monthly channel records");
  });
  it("prefers a share's own segment base over the analysis-wide base", () => {
    const a: Analysis = {
      ...analysis("pain-points-by-cohort"),
      unit: "percent",
      denominator: { label: "respondents", value: 600 },
      rows: [{ group: { segment: "Value Seekers" }, value: 10.6, display: "10.6%", denominator: 104 }],
    };
    const m: MetricRef = { ...signal("fit-friction").metrics[0], value: 10.6, display: "10.6%" };
    expect(resolveDenominator(m, a)).toBe(104);
  });
  it("returns null when the row match is ambiguous", () => {
    const a: Analysis = {
      ...analysis("pain-points-by-cohort"),
      rows: [
        { group: { cohort: "A" }, value: 5, display: "5.0%", denominator: 10 },
        { group: { cohort: "B" }, value: 5, display: "5.0%", denominator: 20 },
      ],
    };
    const m: MetricRef = { ...signal("fit-friction").metrics[0], value: 5, display: "5.0%" };
    expect(resolveDenominator(m, a)).toBeNull();
  });
  it("shows no basis without a label or count", () => {
    expect(describeBasis("total", null, null)).toBeNull();
  });
  it("uses one wording per kind of figure", () => {
    expect(describeBasis("share", 400, "Gen Z respondents")?.text).toBe("of 400 Gen Z respondents");
    expect(describeBasis("total", 7, "return records", 30)?.text).toBe("Total across 7 of 30 return records");
    expect(describeBasis("average", 400, "of Gen Z respondents")?.text).toBe("Average of 400 Gen Z respondents");
    expect(describeBasis("derived", 400, "Gen Z respondents")?.label).toBe("Based on");
  });
  it("describes averages and differences by what they are", () => {
    const price = signal("premium-ceiling").metrics[0];
    expect(buildMetricView(price, index).basis).toBe("Average of 400 Gen Z respondents");
    const nps = signal("genz-nps-gap").metrics[0];
    expect(buildMetricView(nps, index).basis).toBe("Based on 400 Gen Z respondents");
    const sales = signal("social-discovery").metrics[1];
    expect(buildMetricView(sales, index).basis).toBe("Total across 6 monthly channel records");
  });
});

describe("numbers are hidden unless recomputed", () => {
  it("hides a metric the backend withheld", () => {
    const m: MetricRef = { ...signal("fit-friction").metrics[0], value: null, display: null };
    const view = buildMetricView(m, index);
    expect(view.visible).toBe(false);
    expect(view.display).toBeNull();
    expect(view.basis).toBeNull();
  });
  it("hides a metric whose analysis did not recompute", () => {
    const mismatch = new Map([["pain-points-by-cohort", { ...analysis("pain-points-by-cohort"), status: "mismatch" as const }]]);
    expect(buildMetricView(signal("fit-friction").metrics[0], mismatch).visible).toBe(false);
  });
  it("shows a derived value only when every input row was recomputed", () => {
    const nps = signal("genz-nps-gap").metrics[0];
    expect(inputsComputed(nps, analysis("nps-by-cohort"))).toBe(true);
    const missing: Analysis = {
      ...analysis("nps-by-cohort"),
      rows: analysis("nps-by-cohort").rows.map((r, i) => (i === 1 ? { ...r, value: null } : r)),
    };
    expect(inputsComputed(nps, missing)).toBe(false);
    expect(buildMetricView(nps, new Map([["nps-by-cohort", missing]])).visible).toBe(false);
  });
  it("hides every number of an item that could not be re-verified", () => {
    const item = { ...signal("fit-friction"), integrity: "unverified" as const };
    expect(metricViews(item, index).every((v) => !v.visible && v.display === null)).toBe(true);
    expect(topMetric(item, index)).toBeNull();
  });
  it("keeps provenance from the recomputed analysis", () => {
    const view = buildMetricView(signal("fit-friction").metrics[0], index);
    expect(view.provenance?.sourceTitle).toBe("Northstar Customer Survey 2026");
  });
});

describe("evidence", () => {
  const ref = signal("fit-friction").evidence[0];
  it("opens a verified passage at the exact span", () => {
    expect(drawerTarget(ref)).toEqual({
      handle: ref.handle,
      childId: ref.child_id,
      charStart: ref.char_start,
      charEnd: ref.char_end,
      quote: ref.quote,
    });
  });
  it("opens a stale passage without a span and hides its quote", () => {
    const stale: EvidenceRef = { ...ref, integrity: "stale", quote: null };
    expect(drawerTarget(stale)).toEqual({ handle: ref.handle });
    expect(evidenceView(stale)).toMatchObject({ kind: "stale", openable: true, quote: null });
  });
  it("cannot open withdrawn evidence", () => {
    const gone: EvidenceRef = { ...ref, integrity: "withdrawn", quote: null };
    expect(drawerTarget(gone)).toBeNull();
    expect(evidenceView(gone).openable).toBe(false);
  });
  it("counts the evidence balance of an opportunity", () => {
    expect(evidenceBalance(opportunity("O1"))).toEqual({ supporting: 5, contradicting: 2, gaps: 2, notCurrent: 0 });
  });
});

describe("rowsMatchedText", () => {
  it("rewrites the stored summary in plain words", () => {
    expect(rowsMatchedText({ summary: "aggregate ; sum(x) ; 24 of 120 rows" })).toBe("24 of 120 records");
    expect(rowsMatchedText({ summary: null })).toBeNull();
  });
});
