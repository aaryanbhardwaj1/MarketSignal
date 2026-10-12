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

function cleanBaseLabel(label: string): string {
  return label.replace(/^of\s+/i, "").trim();
}

/**
 * True when a count metric counts records (respondents, rows) rather than summing a quantity:
 * its matching row's denominator equals its value. Only then does "N of M" read correctly.
 */
export function countsRecords(metric: MetricRef, analysis: Analysis | undefined): boolean {
  if (!analysis || metric.unit !== "count" || metric.value == null) return false;
  return analysis.rows.some((row) => row.value === metric.value && row.denominator === row.value);
}

/**
 * "of 400 Gen Z respondents" (shares and record counts), "across 6 monthly channel rows" (sums,
 * averages, scores), or "Base: <label>" when no count is known.
 */
export function basisText(metric: MetricRef, denominator: number | null, recordCount = false): string | null {
  const label = metric.denominator_label ? cleanBaseLabel(metric.denominator_label) : null;
  if (denominator == null) return label ? `Base: ${label}` : null;
  const joiner = metric.unit === "percent" || recordCount ? "of" : "across";
  return `${joiner} ${formatNumber(denominator)} ${label ?? "records"}`;
}

/** The base alone, for labelled layouts: "400 Gen Z respondents", or the label when no count is known. */
export function baseText(metric: MetricRef, denominator: number | null): string | null {
  const label = metric.denominator_label ? cleanBaseLabel(metric.denominator_label) : null;
  if (denominator == null) return label;
  return `${formatNumber(denominator)} ${label ?? "records"}`;
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
  /** The base without a joining word, for "Base: ..." layouts. */
  base: string | null;
  denominator: number | null;
  provenance: Provenance | null;
  derived: boolean;
}

export function buildMetricView(metric: MetricRef, analyses: AnalysisIndex, index = 0): MetricView {
  const analysis = analyses.get(metric.analysis_id);
  const visible = metric.value != null && metric.display != null && inputsComputed(metric, analysis);
  const denominator = visible ? resolveDenominator(metric, analysis) : null;
  return {
    key: `${metric.analysis_id}-${index}`,
    label: metric.label,
    visible,
    display: visible ? metric.display : null,
    basis: visible ? basisText(metric, denominator, countsRecords(metric, analysis)) : null,
    base: visible ? baseText(metric, denominator) : null,
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

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${formatNumber(count)} ${count === 1 ? one : many}`;
}

// ── recent computed analyses ───────────────────────────────────────────────────────────────

/** "24 of 120 rows" from a stored result summary, as plain "24 of 120 records"; null if absent. */
export function rowsMatchedText(result: Pick<AnalyticsResultSummary, "summary">): string | null {
  const match = result.summary?.match(/(\d[\d,]*) of (\d[\d,]*) rows/);
  if (!match) return null;
  return `${match[1]} of ${match[2]} records`;
}
