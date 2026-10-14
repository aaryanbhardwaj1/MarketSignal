/**
 * View logic for the RAGAS panel (RAG Evaluation, developer tools). Pure functions over the
 * catalog `ragas` section: every number shown comes from the catalog; not-run metrics never
 * yield a number.
 */
import type {
  RagasConfiguration,
  RagasItem,
  RagasMetricDefinition,
  RagasMetricResult,
  RagasNotRunReason,
  RagasRun,
  RagasSection,
  RagasSummary,
} from "@/lib/api/contracts";

export const RAGAS_FRAMING =
  "RAGAS complements MarketSignal's deterministic metrics; it doesn't replace them. Scores are heuristics, not ground truth.";

export const RAGAS_LLM_COMMAND =
  "MS_LIVE_LLM=1 ANTHROPIC_API_KEY=... uv --directory eval/ragas_runner run ragas-eval llm --samples ... --out ... --i-understand-this-calls-the-model";

export const NOT_RUN_REASON: Record<RagasNotRunReason, string> = {
  model_credits_unavailable: "Requires model calls; no model credits are available.",
  no_reference_answers: "Requires authored reference answers.",
};

/** Item scores below this are highlighted as outliers. */
export const RAGAS_LOW_SCORE = 0.5;

export interface RagasFamilies {
  computed: RagasMetricDefinition[];
  modelJudged: RagasMetricDefinition[];
}

/** Splits definitions by family; LLM-judged metrics are always on the model-judged side. */
export function splitFamilies(section: RagasSection): RagasFamilies {
  const modelJudged = section.definitions.filter((d) => d.family === "ragas_llm_judge" || d.needs_llm);
  const computed = section.definitions.filter((d) => !modelJudged.includes(d));
  return { computed, modelJudged };
}

/** The summary of a computed metric, or null for anything not run or missing. */
export function computedSummary(config: RagasConfiguration, key: string): RagasSummary | null {
  const m = config.metrics.find((r) => r.key === key);
  return m && m.status === "computed" && m.summary ? m.summary : null;
}

export function metricResult(config: RagasConfiguration, key: string): RagasMetricResult | undefined {
  return config.metrics.find((r) => r.key === key);
}

/** Not-run reason for a model-judged metric: the stored reason, else inferred from the definition. */
export function notRunReason(section: RagasSection, def: RagasMetricDefinition): string {
  for (const run of section.runs) {
    for (const c of run.configurations) {
      const m = metricResult(c, def.key);
      if (m && m.status === "not_run") return NOT_RUN_REASON[m.not_run_reason];
    }
  }
  return def.needs_reference_answer ? NOT_RUN_REASON.no_reference_answers : NOT_RUN_REASON.model_credits_unavailable;
}

export interface HistogramView {
  categories: string[];
  counts: number[];
}

const binEdge = (v: number) => (Math.round(v * 100) / 100).toFixed(1);

/** Stored histogram bins → chart categories and counts (bins kept exactly as stored). */
export function histogramView(summary: RagasSummary | null): HistogramView {
  const bins = summary?.histogram ?? [];
  return { categories: bins.map((b) => `${binEdge(b.lo)}–${binEdge(b.hi)}`), counts: bins.map((b) => b.n) };
}

export interface ConfigComparisonRow {
  key: string;
  label: string;
  values: { configuration: string; mean: number }[];
}

/** Per-metric pairing across a run's configurations; only metrics computed in every configuration. */
export function configurationComparison(run: RagasRun, defs: RagasMetricDefinition[]): ConfigComparisonRow[] {
  if (run.configurations.length < 2) return [];
  const rows: ConfigComparisonRow[] = [];
  for (const def of defs) {
    const values = run.configurations.map((c) => ({ configuration: c.name, summary: computedSummary(c, def.key) }));
    if (values.every((v) => v.summary !== null)) {
      rows.push({
        key: def.key,
        label: def.label,
        values: values.map((v) => ({ configuration: v.configuration, mean: (v.summary as RagasSummary).mean })),
      });
    }
  }
  return rows;
}

/** Items sorted by one metric ascending (worst first); undefined scores sink to the end. */
export function sortByMetricAscending(items: readonly RagasItem[], key: string): RagasItem[] {
  return [...items].sort((a, b) => {
    const x = a.scores[key];
    const y = b.scores[key];
    if (x == null && y == null) return a.item_id.localeCompare(b.item_id);
    if (x == null) return 1;
    if (y == null) return -1;
    return x - y || a.item_id.localeCompare(b.item_id);
  });
}

export function isLowScore(value: number | null | undefined): boolean {
  return typeof value === "number" && value < RAGAS_LOW_SCORE;
}

/** Plain label for a configuration name ("standard" → "Standard"). */
export function configurationLabel(name: string): string {
  return name ? name.charAt(0).toUpperCase() + name.slice(1) : name;
}

const LABEL_PARTS: [RegExp, string][] = [
  [/evidence pack/g, "pack"],
  [/cited passages/g, "cited"],
  [/text similarity/g, "text"],
];

/** Compact axis label for context metrics ("Context recall (IDs, evidence pack)" → "Recall · IDs, pack"). */
export function shortMetricLabel(def: Pick<RagasMetricDefinition, "label">): string {
  const m = /^Context (recall|precision) \(([^)]*)\)$/.exec(def.label);
  if (!m) return def.label;
  const detail = LABEL_PARTS.reduce((s, [re, to]) => s.replace(re, to), m[2]);
  return `${configurationLabel(m[1])} · ${detail}`;
}

const lowerList = (labels: string[]) =>
  labels.length <= 1 ? (labels[0] ?? "") : `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;

/**
 * One-line reading of a two-configuration comparison, derived from the stored means. It names
 * directions and metrics only, never a number, and says the scores are heuristics.
 */
export function comparisonTakeaway(rows: readonly ConfigComparisonRow[]): string | null {
  if (rows.length === 0 || rows.some((r) => r.values.length !== 2)) return null;
  const [a, b] = rows[0].values.map((v) => configurationLabel(v.configuration));
  const bAhead = rows.filter((r) => r.values[1].mean > r.values[0].mean);
  const aAhead = rows.filter((r) => r.values[0].mean > r.values[1].mean);
  const tail = " These are heuristics over the same items, not proof of better answers.";
  if (bAhead.length === rows.length) return `${b} scores higher than ${a} on every offline metric computed for both.${tail}`;
  if (aAhead.length === rows.length) return `${a} scores higher than ${b} on every offline metric computed for both.${tail}`;
  if (bAhead.length === 0 && aAhead.length === 0) return `${a} and ${b} score the same on every offline metric.${tail}`;
  const lead = bAhead.length > 0 ? { who: b, rows: bAhead, other: a } : { who: a, rows: aAhead, other: b };
  return `${lead.who} scores higher on ${lowerList(lead.rows.map((r) => r.label.toLowerCase()))}; ${lead.other} scores the same or higher on the rest.${tail}`;
}
