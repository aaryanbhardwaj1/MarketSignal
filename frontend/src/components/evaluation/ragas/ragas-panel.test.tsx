import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import catalogJson from "@/lib/api/__fixtures__/evaluation-catalog.json";
import type { EvalCatalog, RagasItem, RagasSection } from "@/lib/api/contracts";
import { formatEvalValue } from "@/lib/eval-view";
import { NOT_RUN_REASON, RAGAS_FRAMING, computedSummary, notRunReason, splitFamilies } from "@/lib/views/ragas";

const ITEMS: RagasItem[] = [
  { phase: "ragas", item_id: "g-high", configuration: "standard", category: "pricing", question: "High?", scores: { id_context_recall_pack: 0.9 } },
  { phase: "ragas", item_id: "g-none", configuration: "standard", category: "pricing", question: "None?", scores: { id_context_recall_pack: null } },
  { phase: "ragas", item_id: "g-low", configuration: "standard", category: "churn", question: "Low?", scores: { id_context_recall_pack: 0.25 } },
];

vi.mock("@/lib/api/hooks/evaluation", () => ({
  useRagasItems: (runId: string | null) => ({
    data: runId ? { run_id: runId, total: ITEMS.length, items: ITEMS } : undefined,
    isPending: runId === null,
    isError: false,
    error: null,
    refetch: () => undefined,
  }),
}));

import { RagasPanel } from "./ragas-panel";
import { RagasItemDetail } from "./ragas-items";

const catalog = catalogJson as unknown as EvalCatalog;
const section = catalog.ragas as RagasSection;
const { computed, modelJudged } = splitFamilies(section);
const html = renderToStaticMarkup(<RagasPanel catalog={catalog} ws="NORTHSTAR" />);
const textOf = (s: string) =>
  s
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"');

/** Markup of the first element carrying `attr`, up to its closing `</tag>`. */
function block(attr: string, tag: string): string {
  const start = html.indexOf(attr);
  expect(start).toBeGreaterThan(-1);
  return html.slice(start, html.indexOf(`</${tag}>`, start));
}

describe("RagasPanel", () => {
  it("frames RAGAS as a complement and states offline provenance", () => {
    const text = textOf(html);
    expect(text).toContain(RAGAS_FRAMING);
    expect(text).toContain(`ragas ${section.ragas_version}`);
    expect(text).toContain("telemetry disabled");
    expect(text).toContain("no model calls");
    expect(text).toContain("Computed offline");
    expect(text).toContain("Model-judged");
  });

  it("shows every model-judged metric as not run, with its reason and no number", () => {
    expect(modelJudged.length).toBeGreaterThan(0);
    for (const def of modelJudged) {
      const text = textOf(block(`data-model-judged="${def.key}"`, "li"));
      expect(text).toContain("Not yet run");
      expect(text).toContain(notRunReason(section, def));
      // The stored description may name a statistic (e.g. "F1"); the rendered values carry no number.
      expect(text.replace(def.what_it_measures, "")).not.toMatch(/\d/);
    }
    expect(textOf(html)).toContain(NOT_RUN_REASON.no_reference_answers);
    expect(html).toContain("--i-understand-this-calls-the-model");
    for (const def of modelJudged) expect(html).not.toContain(`data-metric-mean="${def.key}"`);
  });

  it("shows computed means exactly as stored in the catalog", () => {
    const shown = [...html.matchAll(/data-metric-mean="([^"]+)">([^<]+)</g)].map((m) => [m[1], m[2]]);
    const expected: [string, string][] = [];
    for (const run of section.runs)
      for (const def of computed)
        for (const c of run.configurations) {
          const summary = computedSummary(c, def.key);
          if (summary) expected.push([def.key, formatEvalValue(summary.mean, "ratio")]);
        }
    expect(expected.length).toBeGreaterThan(0);
    expect(shown).toEqual(expected);
    for (const [, v] of shown) expect(v).toMatch(/^\d\.\d{3}$/);
  });

  it("compares Standard vs Research only for the run that has both", () => {
    const comparisons = html.match(/data-testid="ragas-comparison"/g) ?? [];
    expect(comparisons).toHaveLength(section.runs.filter((r) => r.configurations.length > 1).length);
    const p4 = html.slice(html.indexOf('data-run="ragas-p4-research-test"'));
    expect(p4).toContain('data-testid="ragas-comparison"');
    expect(textOf(p4)).toContain("Standard vs Research");
    const p3 = html.slice(html.indexOf('data-run="ragas-p3-live-v0"'), html.indexOf('data-run="ragas-p4-research-test"'));
    expect(p3).not.toContain('data-testid="ragas-comparison"');
  });

  it("shows the reconciliation caveat with its four sourced numbers", () => {
    const caveat = section.caveats.find((c) => c.id === "ragas-id-recall-counts-alternates")!;
    expect(caveat.metrics).toHaveLength(4);
    const card = block(`data-caveat="${caveat.id}"`, "ul");
    for (const m of caveat.metrics) expect(textOf(card)).toContain(formatEvalValue(m.value, m.unit));
    expect(textOf(html)).toContain("Low ID precision over the evidence pack is expected");
  });

  it("lists items lowest score first, highlights low scores and puts undefined last", () => {
    const table = html.slice(html.indexOf("<table"));
    const order = ["g-low", "g-high", "g-none"].map((id) => table.indexOf(id));
    expect(order.every((i) => i > -1)).toBe(true);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    expect(table).toContain('data-low="true"');
    expect(textOf(table)).toContain("Not scorable");
  });

  it("drawer detail shows question, category, configuration and all scores", () => {
    const detail = textOf(renderToStaticMarkup(<RagasItemDetail item={ITEMS[2]} defs={computed} />));
    expect(detail).toContain("Low?");
    expect(detail).toContain("Churn");
    expect(detail).toContain("Standard");
    for (const def of computed) expect(detail).toContain(def.label);
    expect(detail).toContain("0.250");
    expect(detail).toContain("Below 0.5");
  });

  it("says plainly when the catalog has no RAGAS section", () => {
    const bare = { ...catalog, ragas: undefined };
    const text = textOf(renderToStaticMarkup(<RagasPanel catalog={bare} />));
    expect(text).toContain("RAGAS not yet run");
    expect(text).not.toMatch(/\d/);
  });
});
