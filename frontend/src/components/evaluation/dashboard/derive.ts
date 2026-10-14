/**
 * Pure derivations for the RAG Evaluation dashboard (header strip, overview story cards,
 * grounding gates, research takeaway). Everything here selects and labels catalog values;
 * no figure is computed, rounded or invented. Anything the catalog lacks is left out.
 */
import type { StatusTone } from "@/components/ui/tone";
import type { EvalCatalog, EvalMetric, EvalRunId } from "@/lib/api/contracts";
import { crossesZero, deltaVerdict, metricById, provenanceForRun, type EvalTabId } from "@/lib/eval-view";

type Gate = EvalCatalog["grounded"]["hard_gates"][number];
type Decision = EvalCatalog["retrieval"]["decisions"][number];
type Tradeoff = EvalCatalog["research_tradeoff"][number];
type Comparison = EvalCatalog["retrieval"]["comparisons"][number];

// ── Header: current evaluated configuration ───────────────────────────────────────────────

export interface EvaluatedSet {
  dataset: string;
  version: string | null;
  splits: { runId: EvalRunId; split: string | null; questions: number }[];
}

/** Datasets with version, splits and question counts, from the failure-run index and run provenance. */
export function evaluatedSets(c: EvalCatalog): EvaluatedSet[] {
  const sets = new Map<string, EvaluatedSet>();
  for (const run of c.failure_runs) {
    const p = provenanceForRun(c, run.run_id);
    if (!p) continue;
    const key = p.dataset.name;
    if (!sets.has(key)) sets.set(key, { dataset: key, version: p.dataset.version, splits: [] });
    sets.get(key)!.splits.push({ runId: run.run_id, split: p.split, questions: run.item_count });
  }
  return [...sets.values()];
}

/** Distinct generation models recorded in run provenance (retrieval runs have none). */
export function evaluatedModels(c: EvalCatalog): string[] {
  const all = [
    c.grounded.provenance.model,
    ...c.research_tradeoff.map((r) => r.provenance.model),
    ...c.analytics.map((a) => a.provenance.model),
  ];
  return [...new Set(all.filter((m): m is string => !!m))];
}

const RERANK_DECISION = "reranker-rejected";

/** Production retrieval as recorded: the default arm, and whether the reranker was turned down. */
export function productionRetrieval(
  c: EvalCatalog,
): { label: string; rerankerOff: boolean; reranker: Decision | undefined } | null {
  const arm = c.retrieval.runs.flatMap((r) => r.arms).find((a) => a.is_default);
  if (!arm) return null;
  const reranker = c.retrieval.decisions.find((d) => d.id === RERANK_DECISION);
  const rerankerOff = !/rerank/.test(arm.arm) && !!reranker && reranker.outcome !== "adopted";
  return { label: arm.label.replace(/\s*\(.*\)\s*$/, ""), rerankerOff, reranker };
}

// ── Overview story cards ──────────────────────────────────────────────────────────────────

export type StoryFigure =
  | { kind: "metric"; metric: EvalMetric; signed?: boolean }
  | { kind: "pair"; label: string; standard: EvalMetric; research: EvalMetric };

export interface StoryCard {
  id: "hybrid" | "reranker" | "citations" | "research";
  title: string;
  verdict: string;
  tone: StatusTone;
  figures: StoryFigure[];
  /** One sentence from the catalog's own decision text, or a reading of the recorded CIs. */
  summary?: string;
  tab: EvalTabId;
}

/** A hard gate shown with the metric bits: "k / n" with its source. */
export function gateMetric(g: Gate): EvalMetric {
  return { id: `gate.${g.id}`, label: g.label, value: g.k, unit: "count", k: g.k, n: g.n, source: g.source };
}

function comparison(c: EvalCatalog, split: string, a: string, b: string): Comparison | undefined {
  const run = c.retrieval.runs.find((r) => r.provenance.split === split);
  return run && c.retrieval.comparisons.find((x) => x.run_id === run.run_id && x.a === a && x.b === b);
}

const deltaOf = (cmp: Comparison | undefined, suffix: string) => cmp?.metrics.find((m) => m.id.endsWith(`.${suffix}`));

function hybridCard(c: EvalCatalog): StoryCard | null {
  const d = deltaOf(comparison(c, "test", "dense", "hybrid"), "d_recall@10");
  if (!d) return null;
  const v = deltaVerdict(d);
  const wins = v.distinguishable && v.tone === "success";
  const recall = metricById(c.overview.headline, "headline.test_hybrid_recall10");
  return {
    id: "hybrid",
    title: wins ? "Hybrid beats dense on held-out recall" : "Hybrid and dense are not distinguishable on held-out recall",
    verdict: v.label,
    tone: wins ? "success" : "neutral",
    figures: [{ kind: "metric", metric: d, signed: true }, ...(recall ? [{ kind: "metric" as const, metric: recall }] : [])],
    tab: "retrieval",
  };
}

function rerankerCard(c: EvalCatalog): StoryCard | null {
  const decision = c.retrieval.decisions.find((d) => d.id === RERANK_DECISION);
  if (!decision) return null;
  const adopted = decision.outcome === "adopted";
  return {
    id: "reranker",
    title: adopted ? "Reranker adopted" : "Reranker rejected",
    verdict: adopted ? "Adopted" : "Negative finding",
    tone: adopted ? "success" : "warn",
    figures: decision.metrics.map((m) => ({ kind: "metric", metric: m, signed: true })),
    summary: decision.text,
    tab: "retrieval",
  };
}

const CITATION_GATES = ["citation_resolvability", "citation_in_pack"];

function citationCard(c: EvalCatalog): StoryCard | null {
  const gates = CITATION_GATES.map((id) => c.grounded.hard_gates.find((g) => g.id === id)).filter((g): g is Gate => !!g);
  if (gates.length === 0) return null;
  const pass = gates.every((g) => g.pass);
  const leaks = metricById(c.grounded.metrics, "p3.cross_workspace_leaks");
  return {
    id: "citations",
    title: pass ? "Every citation resolves and stays in the evidence pack" : "Citation integrity gate failed",
    verdict: pass ? "All gates pass" : "Gate failed",
    tone: pass ? "success" : "danger",
    figures: [...gates.map((g) => ({ kind: "metric" as const, metric: gateMetric(g) })), ...(leaks ? [{ kind: "metric" as const, metric: leaks }] : [])],
    tab: "grounded",
  };
}

const rowOf = (t: Tradeoff | undefined, id: string) => t?.rows.find((r) => r.id === id);

function researchCard(c: EvalCatalog): StoryCard | null {
  const t = c.research_tradeoff.find((r) => r.split === "test") ?? c.research_tradeoff[0];
  const cited = rowOf(t, "gold_coverage");
  if (!t || !cited) return null;
  const figures: StoryFigure[] = cited.delta ? [{ kind: "metric", metric: cited.delta, signed: true }] : [];
  for (const id of ["cost_usd", "latency_total_p50"]) {
    const r = rowOf(t, id);
    if (r) figures.push({ kind: "pair", label: r.label, standard: r.standard, research: r.research });
  }
  return {
    id: "research",
    title: "Standard vs Research trade-off",
    verdict: "Trade-off",
    tone: "info",
    figures,
    summary: researchTakeaway(t),
    tab: "research",
  };
}

/** The four headline cards, in story order; any the catalog cannot support are left out. */
export function headlineStory(c: EvalCatalog): StoryCard[] {
  return [hybridCard(c), rerankerCard(c), citationCard(c), researchCard(c)].filter((x): x is StoryCard => !!x);
}

// ── Grounding & safety ────────────────────────────────────────────────────────────────────

type SafetyRule = "zero" | "all" | "record";

/** Safety measures shown beside the hard gates, and how each reads (none expected / all expected / record only). */
export const SAFETY_RULES: { id: string; rule: SafetyRule; severity?: "danger" }[] = [
  { id: "p3.cross_workspace_leaks", rule: "zero", severity: "danger" },
  { id: "p3.insufficient_correct", rule: "all" },
  { id: "p3.over_refusal", rule: "zero" },
  { id: "p3.uncited_numbers_absent", rule: "zero" },
  { id: "p3.cited_units_flagged", rule: "zero" },
  { id: "p3.regenerated", rule: "record" },
  { id: "p3.fallback_after_verification", rule: "record" },
];

export interface SafetyMeasure {
  metric: EvalMetric;
  tone: StatusTone;
  state: string;
}

/** Plain reading of each safety measure present in the catalog; values are never altered. */
export function safetyMeasures(metrics: EvalMetric[]): SafetyMeasure[] {
  const out: SafetyMeasure[] = [];
  for (const rule of SAFETY_RULES) {
    const m = metricById(metrics, rule.id);
    if (!m) continue;
    if (m.value == null) {
      out.push({ metric: m, tone: "neutral", state: "Not measured" });
    } else if (rule.rule === "zero") {
      out.push(m.value === 0 ? { metric: m, tone: "success", state: "None" } : { metric: m, tone: rule.severity ?? "warn", state: rule.severity ? "Fail" : "Review" });
    } else if (rule.rule === "all") {
      const all = m.n != null && m.value === m.n;
      out.push({ metric: m, tone: all ? "success" : "warn", state: all ? "All correct" : "Review" });
    } else {
      out.push({ metric: m, tone: "neutral", state: "Recorded" });
    }
  }
  return out;
}

// ── Standard vs Research ──────────────────────────────────────────────────────────────────

export const EVIDENCE_ROWS = ["gold_handle_recall", "gold_coverage", "answer_completeness"] as const;

/** One-line reading of a split: evidence gains (CI clear of 0) against spend. */
export function researchTakeaway(t: Tradeoff): string {
  const gain = ["gold_handle_recall", "gold_coverage"].every((id) => {
    const d = rowOf(t, id)?.delta;
    return !!d && d.value != null && d.value > 0 && !crossesZero(d) && d.ci_low != null;
  });
  const cost = rowOf(t, "cost_usd")?.delta;
  const lat = rowOf(t, "latency_total_p50");
  const costlier = !!cost && cost.value != null && cost.value > 0 && !crossesZero(cost) && cost.ci_low != null;
  const slower = !!lat && lat.research.value != null && lat.standard.value != null && lat.research.value > lat.standard.value;
  if (gain && costlier && slower) return "Research finds and cites more evidence, but is slower and more expensive.";
  if (!gain && costlier && slower) {
    return "On this split, research's evidence gains are not distinguishable from standard mode, and it is slower and more expensive.";
  }
  return "Research and standard mode trade evidence against cost differently on this split; read the paired differences below.";
}
