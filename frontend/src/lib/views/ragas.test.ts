import { describe, expect, it } from "vitest";
import catalogJson from "@/lib/api/__fixtures__/evaluation-catalog.json";
import type { EvalCatalog, RagasItem, RagasSection } from "@/lib/api/contracts";
import {
  NOT_RUN_REASON,
  comparisonTakeaway,
  computedSummary,
  configurationComparison,
  histogramView,
  isLowScore,
  notRunReason,
  shortMetricLabel,
  sortByMetricAscending,
  splitFamilies,
} from "./ragas";

const section = (catalogJson as unknown as EvalCatalog).ragas as RagasSection;
const p3 = section.runs.find((r) => r.id === "ragas-p3-live-v0")!;
const p4 = section.runs.find((r) => r.id === "ragas-p4-research-test")!;

describe("ragas view", () => {
  it("splits families; model-judged metrics are never in the computed family", () => {
    const { computed, modelJudged } = splitFamilies(section);
    expect(computed.length + modelJudged.length).toBe(section.definitions.length);
    expect(modelJudged.every((d) => d.family === "ragas_llm_judge")).toBe(true);
    expect(computed.every((d) => !d.needs_llm)).toBe(true);
  });

  it("not-run metrics never yield a summary and carry a plain reason", () => {
    const { modelJudged } = splitFamilies(section);
    for (const def of modelJudged) {
      for (const run of section.runs) for (const c of run.configurations) expect(computedSummary(c, def.key)).toBeNull();
      expect(Object.values(NOT_RUN_REASON)).toContain(notRunReason(section, def));
    }
    const faith = modelJudged.find((d) => d.key === "faithfulness")!;
    expect(notRunReason(section, faith)).toBe(NOT_RUN_REASON.model_credits_unavailable);
  });

  it("keeps computed values exactly as stored", () => {
    const stored = p3.configurations[0].metrics.find((m) => m.key === "id_context_recall_pack")!;
    expect(computedSummary(p3.configurations[0], "id_context_recall_pack")).toEqual(stored.summary);
  });

  it("maps stored histogram bins to chart data one-to-one", () => {
    const summary = computedSummary(p4.configurations[0], "id_context_recall_pack")!;
    const view = histogramView(summary);
    expect(view.counts).toEqual(summary.histogram.map((b) => b.n));
    expect(view.categories[0]).toBe("0.0–0.1");
    expect(histogramView(null)).toEqual({ categories: [], counts: [] });
  });

  it("pairs configurations per computed metric only", () => {
    const { computed, modelJudged } = splitFamilies(section);
    const rows = configurationComparison(p4, [...computed, ...modelJudged]);
    expect(rows.map((r) => r.key)).toEqual(computed.map((d) => d.key));
    const recall = rows.find((r) => r.key === "id_context_recall_pack")!;
    expect(recall.values.map((v) => v.configuration)).toEqual(["standard", "research"]);
    expect(recall.values[0].mean).toBe(computedSummary(p4.configurations[0], "id_context_recall_pack")!.mean);
    expect(configurationComparison(p3, computed)).toEqual([]);
  });

  it("sorts worst first with undefined scores last and flags low scores", () => {
    const mk = (id: string, v: number | null): RagasItem => ({
      phase: "ragas",
      item_id: id,
      configuration: "standard",
      category: "c",
      question: "q",
      scores: { m: v },
    });
    const sorted = sortByMetricAscending([mk("a", 0.9), mk("b", null), mk("c", 0.1), mk("d", 0.5)], "m");
    expect(sorted.map((i) => i.item_id)).toEqual(["c", "d", "a", "b"]);
    expect([isLowScore(0.49), isLowScore(0.5), isLowScore(null)]).toEqual([true, false, false]);
  });

  it("derives the comparison takeaway from the stored means without quoting numbers", () => {
    const { computed } = splitFamilies(section);
    const rows = configurationComparison(p4, computed);
    const text = comparisonTakeaway(rows);
    const researchAhead = rows.every((r) => r.values[1].mean > r.values[0].mean);
    expect(text).toContain(researchAhead ? "Research scores higher than Standard on every" : "Research");
    expect(text).not.toMatch(/\d/);
    const swap = (r: (typeof rows)[number]) => ({
      ...r,
      values: r.values.map((v, i) => ({ ...v, mean: r.values[1 - i].mean })),
    });
    const flipped = rows.map(swap);
    expect(comparisonTakeaway(flipped)).toContain(researchAhead ? "Standard scores higher than Research on every" : "Standard");
    const mixed = [rows[0], swap(rows[1])];
    expect(comparisonTakeaway(mixed)).toContain(`higher on ${rows[0].label.toLowerCase()}`);
    expect(comparisonTakeaway([])).toBeNull();
  });

  it("shortens context metric labels for chart axes", () => {
    const def = section.definitions.find((d) => d.key === "id_context_recall_pack")!;
    expect(shortMetricLabel(def)).toBe("Recall · IDs, pack");
    const text = section.definitions.find((d) => d.key === "nonllm_context_precision_pack")!;
    expect(shortMetricLabel(text)).toBe("Precision · text, pack");
    expect(shortMetricLabel({ ...def, label: "Something else" })).toBe("Something else");
  });
});
