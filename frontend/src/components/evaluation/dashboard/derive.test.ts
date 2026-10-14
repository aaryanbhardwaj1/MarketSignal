import { describe, expect, it } from "vitest";
import catalogJson from "@/lib/api/__fixtures__/evaluation-catalog.json";
import type { EvalCatalog, EvalMetric } from "@/lib/api/contracts";
import {
  evaluatedModels,
  evaluatedSets,
  gateMetric,
  headlineStory,
  productionRetrieval,
  researchTakeaway,
  safetyMeasures,
  type StoryFigure,
} from "./derive";

const catalog = catalogJson as unknown as EvalCatalog;

const metricIds = (figs: StoryFigure[]) => figs.flatMap((f) => (f.kind === "metric" ? [f.metric] : [f.standard, f.research]));

describe("header configuration", () => {
  it("lists datasets with versions, splits and question counts from the catalog", () => {
    const sets = evaluatedSets(catalog);
    expect(sets.map((s) => s.dataset)).toEqual(["retrieval-v0", "grounded-v0", "research-v0", "analytics-v0"]);
    for (const s of sets) {
      for (const sp of s.splits) {
        expect(sp.questions).toBe(catalog.failure_runs.find((r) => r.run_id === sp.runId)!.item_count);
      }
    }
    expect(sets[0].splits.map((s) => [s.split, s.questions])).toEqual([
      ["dev", catalog.retrieval.runs[0].n],
      ["test", catalog.retrieval.runs[1].n],
    ]);
  });

  it("reports only models recorded in provenance", () => {
    expect(evaluatedModels(catalog)).toEqual([catalog.grounded.provenance.model]);
    const none = {
      ...catalog,
      grounded: { ...catalog.grounded, provenance: { ...catalog.grounded.provenance, model: null } },
      research_tradeoff: [],
      analytics: [],
    };
    expect(evaluatedModels(none)).toEqual([]);
  });

  it("reads the production default arm and the reranker decision", () => {
    const p = productionRetrieval(catalog)!;
    expect(p.label).toBe("Hybrid");
    expect(p.rerankerOff).toBe(true);
    expect(p.reranker?.outcome).toBe("rejected");
  });
});

describe("headline story", () => {
  const cards = headlineStory(catalog);
  const byId = Object.fromEntries(cards.map((c) => [c.id, c]));

  it("tells the four-part story in order", () => {
    expect(cards.map((c) => c.id)).toEqual(["hybrid", "reranker", "citations", "research"]);
  });

  it("uses the held-out dense → hybrid Recall@10 delta exactly as recorded", () => {
    const cmp = catalog.retrieval.comparisons.find((c) => c.run_id === "p2-test-c3" && c.a === "dense" && c.b === "hybrid")!;
    const recorded = cmp.metrics.find((m) => m.id.endsWith(".d_recall@10"))!;
    const fig = byId.hybrid.figures[0] as Extract<StoryFigure, { kind: "metric" }>;
    expect(fig.metric).toBe(recorded);
    expect(fig.metric.value).toBe(recorded.value);
    expect([fig.metric.ci_low, fig.metric.ci_high]).toEqual([recorded.ci_low, recorded.ci_high]);
    expect(byId.hybrid.title).toBe("Hybrid beats dense on held-out recall");
    expect(byId.hybrid.verdict).toBe("Better");
  });

  it("marks the reranker as a negative finding with the decision's own metrics", () => {
    const d = catalog.retrieval.decisions.find((x) => x.id === "reranker-rejected")!;
    expect(byId.reranker.title).toBe("Reranker rejected");
    expect(byId.reranker.tone).toBe("warn");
    expect(metricIds(byId.reranker.figures)).toEqual(d.metrics);
  });

  it("shows citation gates as k / n and the leak count", () => {
    const gates = catalog.grounded.hard_gates.filter((g) => g.id.startsWith("citation_"));
    const figs = metricIds(byId.citations.figures);
    expect(figs.slice(0, 2).map((m) => [m.k, m.n])).toEqual(gates.map((g) => [g.k, g.n]));
    expect(figs[2]).toBe(catalog.grounded.metrics.find((m) => m.id === "p3.cross_workspace_leaks"));
    expect(byId.citations.tone).toBe("success");
  });

  it("pairs research figures from the test split rows", () => {
    const t = catalog.research_tradeoff.find((r) => r.split === "test")!;
    const figs = metricIds(byId.research.figures);
    const row = (id: string) => t.rows.find((r) => r.id === id)!;
    expect(figs).toEqual([row("gold_coverage").delta, row("cost_usd").standard, row("cost_usd").research, row("latency_total_p50").standard, row("latency_total_p50").research]);
  });

  it("flips the story when the catalog says otherwise", () => {
    const flipped: EvalCatalog = {
      ...catalog,
      retrieval: {
        ...catalog.retrieval,
        comparisons: catalog.retrieval.comparisons.map((c) => ({
          ...c,
          metrics: c.metrics.map((m): EvalMetric => ({ ...m, ci_low: -0.1, ci_high: 0.2 })),
        })),
      },
      grounded: {
        ...catalog.grounded,
        hard_gates: catalog.grounded.hard_gates.map((g) => (g.id === "citation_in_pack" ? { ...g, k: g.n - 1, pass: false } : g)),
      },
    };
    const story = Object.fromEntries(headlineStory(flipped).map((c) => [c.id, c]));
    expect(story.hybrid.title).toContain("not distinguishable");
    expect(story.citations.tone).toBe("danger");
    expect(headlineStory({ ...catalog, research_tradeoff: [] }).map((c) => c.id)).not.toContain("research");
  });
});

describe("grounding safety", () => {
  it("wraps a gate as k / n without changing its numbers", () => {
    const g = catalog.grounded.hard_gates[0];
    expect(gateMetric(g)).toMatchObject({ value: g.k, k: g.k, n: g.n, unit: "count", source: g.source });
  });

  it("reads each safety measure plainly", () => {
    const states = Object.fromEntries(safetyMeasures(catalog.grounded.metrics).map((s) => [s.metric.id, [s.state, s.tone]]));
    expect(states["p3.cross_workspace_leaks"]).toEqual(["None", "success"]);
    expect(states["p3.insufficient_correct"]).toEqual(["All correct", "success"]);
    expect(states["p3.over_refusal"]).toEqual(["Review", "warn"]);
    expect(states["p3.regenerated"]).toEqual(["Recorded", "neutral"]);
    const leak = catalog.grounded.metrics.map((m) => (m.id === "p3.cross_workspace_leaks" ? { ...m, value: 1 } : m));
    expect(safetyMeasures(leak)[0]).toMatchObject({ state: "Fail", tone: "danger" });
  });
});

describe("research takeaway", () => {
  it("states the trade-off only when evidence gains clear zero", () => {
    const test = catalog.research_tradeoff.find((r) => r.split === "test")!;
    const dev = catalog.research_tradeoff.find((r) => r.split === "dev")!;
    expect(researchTakeaway(test)).toBe("Research finds and cites more evidence, but is slower and more expensive.");
    expect(researchTakeaway(dev)).toContain("not distinguishable");
  });
});
