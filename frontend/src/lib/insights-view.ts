/**
 * View helpers for the curated analyst brief (Overview and Growth Opportunities). Pure functions,
 * so the display rules are unit-tested: numbers appear only when the backend recomputed them,
 * derived figures only when every input was recomputed, and bases (denominators) come from the
 * recomputed analysis rows, never from copy.
 */
import type {
  Analysis,
  AnalyticsResultSummary,
  EvidenceRef,
  ItemIntegrity,
  MetricRef,
  Opportunity,
  WorkspaceOverview,
} from "@/lib/api/contracts";
import { formatNumber } from "@/lib/format";
import { sourceClass } from "@/lib/labels";

// ── workspace header ───────────────────────────────────────────────────────────────────────

/** "Northstar Athletics - Gen Z Growth Engagement" -> client + engagement (null when absent). */
export function splitWorkspaceName(name: string): { client: string; engagement: string | null } {
  const at = name.indexOf(" - ");
  if (at < 0) return { client: name.trim(), engagement: null };
  const client = name.slice(0, at).trim();
  const engagement = name.slice(at + 3).trim();
  return { client: client || name.trim(), engagement: engagement || null };
}

// ── workspace summary ──────────────────────────────────────────────────────────────────────

/** Display order for source classes: customer first (coverage matters most), then the rest. */
const CLASS_ORDER = ["customer", "market", "competitor", "internal", "financial"];

export interface ClassCount {
  code: string;
  label: string;
  count: number;
}

export function sourceTotal(overview: Pick<WorkspaceOverview, "sources_by_class">): number {
  return Object.values(overview.sources_by_class).reduce((sum, n) => sum + n, 0);
}

/** Non-zero classes in a stable order, with plain-language labels. */
export function classBreakdown(overview: Pick<WorkspaceOverview, "sources_by_class">): ClassCount[] {
  const rank = (code: string) => {
    const i = CLASS_ORDER.indexOf(code);
    return i < 0 ? CLASS_ORDER.length : i;
  };
  return Object.entries(overview.sources_by_class)
    .filter(([, count]) => count > 0)
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
    .map(([code, count]) => ({ code, label: sourceClass(code).label, count }));
}

/**
 * Research runs, split into those that finished normally and those that returned evidence only
 * (live model unavailable), so the headline count does not overstate answered research.
 */
export function researchRunBreakdown(overview: Pick<WorkspaceOverview, "runs">): { total: number; detail: string | null } {
  const states = overview.runs.by_termination_state;
  const completed = states.completed ?? 0;
  const evidenceOnly = states.generation_unavailable ?? 0;
  const parts = [
    completed > 0 ? `${formatNumber(completed)} completed` : null,
    evidenceOnly > 0 ? `${formatNumber(evidenceOnly)} evidence only` : null,
  ].filter((p): p is string => p != null);
  return { total: overview.runs.total, detail: parts.length > 0 ? parts.join(" · ") : null };
}

// ── metrics ────────────────────────────────────────────────────────────────────────────────

export type AnalysisIndex = ReadonlyMap<string, Analysis>;

export function indexAnalyses(analyses: readonly Analysis[] | undefined): AnalysisIndex {
  return new Map((analyses ?? []).map((a) => [a.id, a]));
}

/** `MetricRef.derived.of` entries: `"<analysis_id>:<group values joined by />"`. */
function rowFor(analysis: Analysis, key: string): Analysis["rows"][number] | null {
  const sep = key.indexOf(":");
  if (sep < 0 || key.slice(0, sep) !== analysis.id) return null;
  const groupKey = key.slice(sep + 1);
  return analysis.rows.find((row) => Object.values(row.group).join("/") === groupKey) ?? null;
}

/**
 * True when every input of a derived metric was recomputed: the analysis is `computed` and each
 * referenced row exists with a value. Non-derived metrics need only their analysis computed.
 */
export function inputsComputed(metric: MetricRef, analysis: Analysis | undefined): boolean {
  if (!analysis) return true; // analyses not loaded: rely on the backend's own null-out
  if (analysis.status !== "computed") return false;
  if (!metric.derived) return true;
  return metric.derived.of.every((key) => {
    const row = rowFor(analysis, key);
    return row != null && row.value != null;
  });
}

/**
 * The base a figure was computed over, from the recomputed analysis:
 * - the analysis-wide denominator when one exists;
 * - for a derived difference, the shared per-row denominator of its inputs;
 * - otherwise the denominator of the single row whose value matches the metric.
 * Returns null when it cannot be determined unambiguously (never guessed).
 */
export function resolveDenominator(metric: MetricRef, analysis: Analysis | undefined): number | null {
  if (!analysis || metric.value == null || analysis.status !== "computed") return null;
  if (analysis.denominator) return analysis.denominator.value;
  if (metric.derived) {
    if (metric.derived.op !== "diff") return null;
    const bases = metric.derived.of.map((key) => rowFor(analysis, key)?.denominator ?? null);
    const first = bases[0];
    return first != null && bases.every((b) => b === first) ? first : null;
  }
  const matches = analysis.rows.filter((row) => row.value === metric.value && row.display === metric.display);
  const bases = new Set(matches.map((row) => row.denominator ?? null));
  if (matches.length === 0 || bases.size !== 1) return null;
  return [...bases][0] ?? null;
}

/** Copy-level cleanup of a stored base label: "of Gen Z respondents surveyed" -> "Gen Z respondents surveyed", "rows" -> "records". */
export function cleanBaseLabel(label: string): string {
  return label
    .replace(/^of\s+/i, "")
    .replace(/\brows\b/gi, "records")
    .replace(/\brow\b/gi, "record")
    .trim();
}

/**
 * How a figure relates to its base, which decides the one wording used for it everywhere:
 * - share: a percentage of a population ("27.0% of 400 Gen Z respondents");
 * - records: a count of records out of a population ("108 of 400 Gen Z respondents");
 * - total: a quantity summed over records ("Total across 7 of 30 return records");
 * - average: a mean over records ("Average of 400 Gen Z respondents");
 * - derived: computed from other figures ("Based on 400 Gen Z respondents").
 */
export type BasisKind = "share" | "records" | "total" | "average" | "derived";

export interface Basis {
  /** Short label for labelled layouts ("Out of", "Summed across"). */
  label: string;
  /** The base alone ("400 Gen Z respondents", "7 of 30 return records"). */
  value: string;
  /** One line for compact layouts ("of 400 Gen Z respondents", "Total across 30 return records"). */
  text: string;
}

const BASIS_WORDS: Record<BasisKind, { label: string; lead: string }> = {
  share: { label: "Out of", lead: "of" },
  records: { label: "Out of", lead: "of" },
  total: { label: "Summed across", lead: "Total across" },
  average: { label: "Averaged across", lead: "Average of" },
  derived: { label: "Based on", lead: "Based on" },
};

/**
 * The basis of a figure in plain words. `count` is the base size (null when unknown), `noun` what
 * it counts ("Gen Z respondents"), and `outOf` an enclosing total ("7 of 30 return records").
 * Returns null when there is nothing to say; never guesses a count.
 */
export function describeBasis(
  kind: BasisKind,
  count: number | null,
  noun: string | null,
  outOf: number | null = null,
): Basis | null {
  const words = BASIS_WORDS[kind];
  const what = noun ? cleanBaseLabel(noun) : "records";
  if (count == null) {
    if (!noun) return null;
    return { label: "Based on", value: what, text: `Based on ${what}` };
  }
  const value =
    outOf != null && outOf !== count
      ? `${formatNumber(count)} of ${formatNumber(outOf)} ${what}`
      : `${formatNumber(count)} ${what}`;
  return { label: words.label, value, text: `${words.lead} ${value}` };
}

/** The aggregation the analysis spec ran ("sum", "mean", "count"), read defensively; null if unknown. */
export function aggregationFn(analysis: Pick<Analysis, "spec"> | undefined): string | null {
  const spec = analysis?.spec;
  const first = Array.isArray(spec) ? (spec[0] as { spec?: unknown } | undefined)?.spec : spec;
  const metrics = (first as { metrics?: Array<{ fn?: unknown }> } | null | undefined)?.metrics;
  const fn = Array.isArray(metrics) ? metrics[0]?.fn : undefined;
  return typeof fn === "string" ? fn : null;
}

const FN_KINDS: Record<string, BasisKind> = {
  sum: "total",
  mean: "average",
  avg: "average",
  median: "average",
  count: "records",
  share: "share",
};

/** The basis kind of a figure from its unit, the analysis's aggregation and whether it counts records. */
export function basisKind(
  unit: Analysis["unit"],
  fn: string | null,
  options: { recordCount?: boolean; derived?: boolean } = {},
): BasisKind {
  if (options.derived) return "derived";
  if (unit === "percent") return "share";
  if (unit === "ratio") return "derived";
  const byFn = fn ? FN_KINDS[fn] : undefined;
  if (byFn) return byFn;
  if (unit === "count") return options.recordCount ? "records" : "total";
  if (unit === "score") return "average";
  return "total";
}

/**
 * True when a count metric counts records (respondents, rows) rather than summing a quantity:
 * its matching row's denominator equals its value. Only then does "N of M" read correctly.
 */
export function countsRecords(metric: MetricRef, analysis: Analysis | undefined): boolean {
  if (!analysis || metric.unit !== "count" || metric.value == null) return false;
  if (aggregationFn(analysis) === "count") return true;
  return analysis.rows.some((row) => row.value === metric.value && row.denominator === row.value);
}

/** The basis of a brief figure: "of 400 Gen Z respondents", "Total across 30 return records", "Based on monthly channel records". */
export function metricBasis(metric: MetricRef, denominator: number | null, analysis?: Analysis): Basis | null {
  const kind = basisKind(metric.unit, aggregationFn(analysis), {
    recordCount: countsRecords(metric, analysis),
    derived: metric.derived != null,
  });
  return describeBasis(kind, denominator, metric.denominator_label);
}

export interface Provenance {
  sourceTitle: string;
  sourceCode: string;
  version: number;
  table: string;
  rowsMatched: number | null;
  computedAt: string;
}

export interface MetricView {
  key: string;
  label: string;
  /** False when the figure was not recomputed: show "Could not be re-verified", never a number. */
  visible: boolean;
  display: string | null;
  basis: string | null;
  /** The base without a joining word, for labelled layouts ("Summed across" / "30 return records"). */
  base: string | null;
  /** The label that goes with `base` ("Out of", "Summed across", "Averaged across", "Based on"). */
  baseLabel: string;
  denominator: number | null;
  provenance: Provenance | null;
  derived: boolean;
}

export function buildMetricView(metric: MetricRef, analyses: AnalysisIndex, index = 0): MetricView {
  const analysis = analyses.get(metric.analysis_id);
  const visible = metric.value != null && metric.display != null && inputsComputed(metric, analysis);
  const denominator = visible ? resolveDenominator(metric, analysis) : null;
  const basis = visible ? metricBasis(metric, denominator, analysis) : null;
  return {
    key: `${metric.analysis_id}-${index}`,
    label: metric.label,
    visible,
    display: visible ? metric.display : null,
    basis: basis?.text ?? null,
    base: basis?.value ?? null,
    baseLabel: basis?.label ?? "Based on",
    denominator,
    provenance: analysis
      ? {
          sourceTitle: analysis.provenance.source_title,
          sourceCode: analysis.provenance.source_code,
          version: analysis.provenance.version,
          table: analysis.provenance.table,
          rowsMatched: analysis.provenance.rows_matched,
          computedAt: analysis.provenance.computed_at,
        }
      : null,
    derived: metric.derived != null,
  };
}

/** Item-level gate: an item that could not be re-verified shows no numbers at all. */
export function numbersAllowed(integrity: ItemIntegrity): boolean {
  return integrity !== "unverified";
}

export function metricViews(
  item: { metrics: MetricRef[]; integrity: ItemIntegrity },
  analyses: AnalysisIndex,
): MetricView[] {
  const views = item.metrics.map((m, i) => buildMetricView(m, analyses, i));
  if (numbersAllowed(item.integrity)) return views;
  return views.map((v) => ({ ...v, visible: false, display: null, basis: null, base: null, denominator: null }));
}

/** The first figure that can be shown, for compact summaries. */
export function topMetric(
  item: { metrics: MetricRef[]; integrity: ItemIntegrity },
  analyses: AnalysisIndex,
): MetricView | null {
  return metricViews(item, analyses).find((v) => v.visible) ?? null;
}

// ── evidence ───────────────────────────────────────────────────────────────────────────────

export type EvidenceViewKind = "verified" | "stale" | "withdrawn";

export interface EvidenceView {
  kind: EvidenceViewKind;
  /** Whether the passage can be opened in the evidence drawer. */
  openable: boolean;
  /** The verified quote; null when it could not be re-verified. */
  quote: string | null;
  sourceTitle: string;
  locator: string;
}

export function evidenceView(ref: EvidenceRef): EvidenceView {
  const kind: EvidenceViewKind = ref.integrity;
  return {
    kind,
    openable: kind !== "withdrawn",
    quote: kind === "verified" ? ref.quote : null,
    sourceTitle: ref.source.title,
    locator: ref.locator_label,
  };
}

/** Drawer target for a cited passage: exact span when verified, the passage alone when stale. */
export function drawerTarget(ref: EvidenceRef): {
  handle: string;
  childId?: string;
  charStart?: number;
  charEnd?: number;
  quote?: string;
} | null {
  if (ref.integrity === "withdrawn") return null;
  if (ref.integrity === "stale") return { handle: ref.handle };
  return {
    handle: ref.handle,
    ...(ref.child_id ? { childId: ref.child_id } : {}),
    ...(ref.char_start != null ? { charStart: ref.char_start } : {}),
    ...(ref.char_end != null ? { charEnd: ref.char_end } : {}),
    ...(ref.quote ? { quote: ref.quote } : {}),
  };
}

export interface EvidenceBalance {
  supporting: number;
  contradicting: number;
  gaps: number;
  /** References whose passage is no longer available or changed since the brief. */
  notCurrent: number;
}

export function evidenceBalance(opportunity: Opportunity): EvidenceBalance {
  const all = [...opportunity.supporting, ...opportunity.contradicting];
  return {
    supporting: opportunity.supporting.length,
    contradicting: opportunity.contradicting.length,
    gaps: opportunity.gaps.length,
    notCurrent: all.filter((e) => e.integrity !== "verified").length,
  };
}

// ── recent computed analyses ───────────────────────────────────────────────────────────────

/** "24 of 120 rows" from a stored result summary, as plain "24 of 120 records"; null if absent. */
export function rowsMatchedText(result: Pick<AnalyticsResultSummary, "summary">): string | null {
  const match = result.summary?.match(/(\d[\d,]*) of (\d[\d,]*) rows/);
  if (!match) return null;
  return `${match[1]} of ${match[2]} records`;
}
