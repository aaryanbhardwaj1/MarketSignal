import { describe, expect, it } from "vitest";
import analysesFixture from "@/lib/api/__fixtures__/insights-analyses.json";
import briefFixture from "@/lib/api/__fixtures__/insights-brief.json";
import type { AnalysesResponse, EvidenceRef, InsightsBrief, MetricRef, Signal } from "@/lib/api/contracts";
import { indexAnalyses } from "@/lib/insights-view";
import { insightsDeckHref } from "@/lib/routes";
import {
  INSIGHT_CATEGORIES,
  categoryCounts,
  deckSelectionFor,
  evidenceTotals,
  groupSignals,
  outlookNature,
  parseDeckSelection,
  possessive,
  relatedLinks,
  statusCounts,
  strongestMetric,
  uniqueSources,
} from "./insights";

const brief = briefFixture as unknown as InsightsBrief;
const analyses = indexAnalyses((analysesFixture as unknown as AnalysesResponse).analyses);
const signal = (id: string): Signal => brief.signals.find((s) => s.id === id)!;

describe("categories and grouping", () => {
  it("lists the six categories in the product order", () => {
    expect(INSIGHT_CATEGORIES.map((c) => c.label)).toEqual([
      "Strategic Opportunities",
      "Emerging Signals",
      "Risks / Blockers",
      "Competitor Findings",
      "Optimization Opportunities",
      "Future Outlook",
    ]);
  });

  it("groups signals by kind, keeping curated order, and sets aside unclassified v1 items", () => {
    const v1 = { ...signal("fit-friction"), id: "v1-item", kind: null };
    const { byKind, unclassified } = groupSignals([...brief.signals, v1]);
    expect(byKind.emerging_signal).toHaveLength(4);
    expect(byKind.risk_blocker).toHaveLength(5);
    expect(byKind.competitor_finding).toHaveLength(4);
    expect(byKind.optimization).toHaveLength(4);
    expect(byKind.future_outlook).toHaveLength(4);
    expect(byKind.optimization[0]?.id).toBe("fit-friction");
    expect(unclassified.map((s) => s.id)).toEqual(["v1-item"]);
  });

  it("counts every category from the brief, opportunities included", () => {
    const counts = categoryCounts(brief);
    expect(counts).toEqual({
      opportunities: 4,
      emerging_signal: 4,
      risk_blocker: 5,
      competitor_finding: 4,
      optimization: 4,
      future_outlook: 4,
    });
  });

  it("counts statuses in a fixed order and omits zero counts", () => {
    const counts = statusCounts(brief.signals);
    expect(counts.map((c) => c.status)).toEqual(["strong_evidence", "emerging", "mixed_evidence", "needs_validation"]);
    expect(counts.reduce((n, c) => n + c.count, 0)).toBe(21);
    expect(counts.find((c) => c.status === "strong_evidence")?.count).toBe(10);
    expect(statusCounts([signal("fit-friction")])).toEqual([{ status: "strong_evidence", label: "Strong evidence", count: 1 }]);
  });

  it("sums verified supporting and contradicting references", () => {
    const totals = evidenceTotals(brief.signals);
    expect(totals.supporting).toBe(brief.signals.reduce((n, s) => n + s.support_count, 0));
    expect(totals.contradicting).toBe(brief.signals.reduce((n, s) => n + s.contradiction_count, 0));
    expect(totals.withContradictions).toBe(brief.signals.filter((s) => s.contradiction_count > 0).length);
  });
});

describe("strongestMetric", () => {
  it("prefers a recomputed figure with a known base", () => {
    const m = strongestMetric(signal("fit-friction"), analyses);
    expect(m?.display).toBe("27.0%");
    expect(m?.base).toMatch(/Gen Z respondents/);
  });

  it("returns null when the signal has no figures", () => {
    expect(strongestMetric(signal("competitor-fit-tech"), analyses)).toBeNull();
  });

  it("withholds every figure when the item could not be re-verified", () => {
    expect(strongestMetric({ ...signal("fit-friction"), integrity: "unverified" }, analyses)).toBeNull();
  });

  it("skips figures that were not recomputed", () => {
    const s = signal("fit-friction");
    const metrics: MetricRef[] = s.metrics.map((m, i) => (i === 0 ? { ...m, value: null, display: null } : m));
    expect(strongestMetric({ ...s, metrics }, analyses)?.display).toBe("19.0%");
  });
});

describe("outlookNature", () => {
  it("is a forecast attributed to the source that states the projection", () => {
    const nature = outlookNature(signal("category-growth-outlook"));
    expect(nature.type).toBe("forecast");
    expect(nature.sources.length).toBeGreaterThan(0);
  });

  it("is a hypothesis when no cited passage states a projection", () => {
    expect(outlookNature(signal("creator-discovery-outlook"))).toEqual({ type: "hypothesis", sources: [] });
  });

  it("does not attribute a forecast to a withdrawn passage", () => {
    const s = signal("category-growth-outlook");
    const evidence = s.evidence.map((e): EvidenceRef => ({ ...e, integrity: "withdrawn" }));
    expect(outlookNature({ ...s, evidence }).type).toBe("hypothesis");
  });
});

describe("sources and related links", () => {
  it("lists each cited source once, opening its first passage", () => {
    const s = signal("fit-friction");
    const doubled = { ...s, evidence: [...s.evidence, s.evidence[0]!] };
    const sources = uniqueSources(doubled);
    expect(sources).toHaveLength(3);
    expect(sources[0]?.title).toBe("Northstar Athletics Brand Strategy 2026");
  });

  it("builds titled links to related analyses, opportunities and insights", () => {
    const links = relatedLinks("NORTHSTAR", signal("fit-friction"), brief, analyses);
    const opp = links.find((l) => l.kind === "opportunity");
    expect(opp).toMatchObject({ label: "Cross-category Fit Promise", href: "/w/NORTHSTAR/opportunities/O1" });
    const insight = links.find((l) => l.kind === "insight");
    expect(insight?.href).toBe("/w/NORTHSTAR/insights#fit-returns");
    const analysis = links.find((l) => l.kind === "analysis");
    expect(analysis?.href).toMatch(/^\/w\/NORTHSTAR\/analytics\//);
    expect(analysis?.label).not.toBe(analysis?.href);
  });
});

describe("deck selection", () => {
  it("round-trips through the deck href", () => {
    const selection = { signals: ["fit-friction", "a b/c"], opportunities: ["O1"], analyses: ["x&y"] };
    const href = insightsDeckHref("NORTHSTAR", selection);
    expect(href.startsWith("/w/NORTHSTAR/insights/deck?s=")).toBe(true);
    const query = new URLSearchParams(href.split("?")[1]);
    expect(parseDeckSelection(query)).toEqual(selection);
  });

  it("drops empty and duplicate ids and omits empty lists", () => {
    expect(insightsDeckHref("NORTHSTAR", { signals: ["a", "", "a"], opportunities: [] })).toBe(
      "/w/NORTHSTAR/insights/deck?s=a",
    );
    expect(insightsDeckHref("NORTHSTAR", {})).toBe("/w/NORTHSTAR/insights/deck");
    expect(parseDeckSelection(new URLSearchParams("s=,a,,a&o="))).toEqual({ signals: ["a"], opportunities: [], analyses: [] });
  });

  it("uses the selection, or every strategic opportunity when nothing is selected", () => {
    expect(deckSelectionFor(brief, new Set())).toEqual({
      signals: [],
      opportunities: ["O1", "O2", "O3", "O4"],
      analyses: [],
    });
    expect(deckSelectionFor(brief, new Set(["s:fit-friction", "o:O2"]))).toEqual({
      signals: ["fit-friction"],
      opportunities: ["O2"],
      analyses: [],
    });
  });
});

describe("possessive", () => {
  it("adds the right apostrophe", () => {
    expect(possessive("Northstar")).toBe("Northstar's");
    expect(possessive("Northstar Athletics")).toBe("Northstar Athletics'");
  });
});
