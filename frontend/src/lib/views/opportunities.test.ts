import { describe, expect, it } from "vitest";
import analysesFixture from "@/lib/api/__fixtures__/insights-analyses.json";
import briefFixture from "@/lib/api/__fixtures__/insights-brief.json";
import type { AnalysesResponse, EvidenceRef, InsightsBrief, MetricRef, Opportunity } from "@/lib/api/contracts";
import { indexAnalyses } from "@/lib/insights-view";
import {
  OPPORTUNITY_STATUS_ORDER,
  comparableGroups,
  formatMetricValue,
  gapLabel,
  investigateHref,
  leadSignal,
  opportunityDeckHref,
  orderEvidence,
  orderOpportunities,
  relatedLinks,
  shortQuote,
  sourceMix,
  splitMeasure,
} from "./opportunities";

const brief = briefFixture as unknown as InsightsBrief;
const index = indexAnalyses((analysesFixture as unknown as AnalysesResponse).analyses);
const byId = (id: string): Opportunity => brief.opportunities.find((o) => o.id === id)!;

describe("orderOpportunities", () => {
  it("orders by status strength: supported, mixed, emerging, needs validation", () => {
    const shuffled = [byId("O4"), byId("O3"), byId("O1"), byId("O2")];
    expect(orderOpportunities(shuffled).map((o) => o.status)).toEqual(OPPORTUNITY_STATUS_ORDER);
  });

  it("keeps served order within a status and does not mutate its input", () => {
    const a = { ...byId("O1"), id: "A" };
    const b = { ...byId("O1"), id: "B" };
    const input = [byId("O4"), a, b];
    const out = orderOpportunities(input);
    expect(out.map((o) => o.id)).toEqual(["A", "B", "O4"]);
    expect(input.map((o) => o.id)).toEqual(["O4", "A", "B"]);
  });
});

describe("orderEvidence", () => {
  it("puts verified passages first, then changed, then withdrawn, stably", () => {
    const base = byId("O1").supporting[0];
    const refs: EvidenceRef[] = [
      { ...base, handle: "w", integrity: "withdrawn" },
      { ...base, handle: "v1" },
      { ...base, handle: "s", integrity: "stale" },
      { ...base, handle: "v2" },
    ];
    expect(orderEvidence(refs).map((r) => r.handle)).toEqual(["v1", "v2", "s", "w"]);
  });
});

describe("leadSignal", () => {
  it("prefers the first recomputed figure with a known base", () => {
    const lead = leadSignal(byId("O1"), index);
    expect(lead.kind).toBe("metric");
    if (lead.kind === "metric") {
      expect(lead.metric.display).toBe("27.0%");
      expect(lead.metric.basis).toContain("400");
    }
  });

  it("falls back to the lead supporting passage when there is no figure", () => {
    const o = { ...byId("O1"), metrics: [] };
    const lead = leadSignal(o, index);
    expect(lead.kind).toBe("quote");
    if (lead.kind === "quote") expect(lead.source).toBe(o.supporting.find((r) => r.integrity === "verified")!.source.title);
  });

  it("withholds figures on an item that could not be re-verified", () => {
    const o: Opportunity = {
      ...byId("O1"),
      integrity: "unverified",
      supporting: byId("O1").supporting.map((r) => ({ ...r, integrity: "stale" as const, quote: null })),
    };
    expect(leadSignal(o, index).kind).toBe("withheld");
  });

  it("reports nothing when there is neither a figure nor a passage", () => {
    expect(leadSignal({ ...byId("O1"), metrics: [], supporting: [] }, index).kind).toBe("none");
  });
});

describe("shortQuote", () => {
  it("keeps short text and cuts long text at a word boundary", () => {
    expect(shortQuote("Short passage.")).toBe("Short passage.");
    const long = "word ".repeat(60).trim();
    const out = shortQuote(long, 40);
    expect(out.length).toBeLessThanOrEqual(41);
    expect(out.endsWith("…")).toBe(true);
    expect(out).not.toMatch(/\s…$/);
  });
});

describe("sourceMix", () => {
  it("counts cited passages by source class in a fixed order", () => {
    const mix = sourceMix(byId("O2"));
    expect(mix.map((m) => m.label)).toEqual(["Customer", "Competitor", "Market", "Internal"]);
    expect(mix.reduce((n, m) => n + m.count, 0)).toBe(byId("O2").supporting.length + byId("O2").contradicting.length);
    expect(mix.find((m) => m.code === "internal")?.count).toBe(7);
  });

  it("drops empty classes and labels unknown ones plainly", () => {
    const base = byId("O4").supporting[0];
    const mix = sourceMix({ ...byId("O4"), supporting: [{ ...base, source: { ...base.source, source_class: "other" } }], contradicting: [] });
    expect(mix).toEqual([{ code: "other", label: "Other", count: 1 }]);
  });
});

describe("gapLabel", () => {
  it("counts open gaps in plain words", () => {
    expect(gapLabel(0)).toBe("No open gaps");
    expect(gapLabel(1)).toBe("1 open gap");
    expect(gapLabel(2)).toBe("2 open gaps");
  });
});

describe("links", () => {
  it("prefills the chat composer with the investigation question", () => {
    expect(investigateHref("NORTHSTAR", "Does it work? 50% & more")).toBe(
      "/w/NORTHSTAR/ask?q=Does%20it%20work%3F%2050%25%20%26%20more",
    );
  });

  it("builds the deck link with the opportunity and its related insights and analyses", () => {
    const o = byId("O4");
    expect(opportunityDeckHref("NORTHSTAR", o)).toBe(
      "/w/NORTHSTAR/insights/deck?s=sustainability-proof&o=O4&a=genz-top-pain-points",
    );
  });

  it("resolves related insight and analysis titles, skipping unknown ids", () => {
    const o = { ...byId("O4"), related: { analyses: ["genz-top-pain-points", "nope"], opportunities: [], signals: ["sustainability-proof", "gone"] } };
    const links = relatedLinks("NORTHSTAR", o, brief.signals, index);
    expect(links.insights).toHaveLength(1);
    expect(links.insights[0].href).toBe("/w/NORTHSTAR/insights#sustainability-proof");
    expect(links.analyses).toHaveLength(1);
    expect(links.analyses[0].href).toBe("/w/NORTHSTAR/analytics/genz-top-pain-points");
    expect(links.analyses[0].title).not.toBe("genz-top-pain-points");
  });
});

describe("comparable figures", () => {
  it("splits a label into its measure and group", () => {
    expect(splitMeasure("Lack of personalization is the top frustration, aged 28+")).toEqual({
      measure: "Lack of personalization is the top frustration",
      group: "Aged 28+",
    });
    expect(splitMeasure("Q3 returns: fit runs large")).toEqual({ measure: "Q3 returns: fit runs large", group: null });
  });

  it("groups figures of one measure and unit so they can be charted together", () => {
    const { groups, singles } = comparableGroups(byId("O2"), index);
    expect(groups).toHaveLength(1);
    expect(groups[0].measure).toBe("Lack of personalization is the top frustration");
    expect(groups[0].items.map((i) => i.group)).toEqual(["Gen Z", "Aged 28+", "Value Seekers"]);
    expect(singles).toHaveLength(0);
  });

  it("leaves unrelated figures as single figures", () => {
    const { groups, singles } = comparableGroups(byId("O1"), index);
    expect(groups).toHaveLength(0);
    expect(singles).toHaveLength(3);
  });

  it("never charts derived figures or figures that were not recomputed", () => {
    const o = byId("O2");
    const withheld: MetricRef = { ...o.metrics[1], value: null, display: null };
    const { groups, singles } = comparableGroups({ ...o, metrics: [o.metrics[0], withheld, o.metrics[2]] }, index);
    expect(groups[0].items).toHaveLength(2);
    expect(singles.map((s) => s.visible)).toEqual([false]);
  });

  it("formats chart values by unit", () => {
    expect(formatMetricValue("percent", 7)).toBe("7.0%");
    expect(formatMetricValue("usd", 61.6)).toBe("$61.60");
    expect(formatMetricValue("count", 5085)).toBe("5,085");
  });
});
