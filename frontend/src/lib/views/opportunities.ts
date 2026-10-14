/**
 * View logic for Growth Opportunities (list and detail). Pure functions, so the display rules are
 * unit-tested: a fixed status order, which figure leads a summary, the source mix of the cited
 * evidence, comparable figures that may share a chart, and the cross-surface links. Numbers come
 * only from `lib/insights-view` metric views, which already withhold anything not recomputed.
 */
import type { AnalysisUnit, EvidenceRef, Opportunity, OpportunityStatus, Signal } from "@/lib/api/contracts";
import { formatCount, formatNumber, formatUsd } from "@/lib/format";
import { metricViews, numbersAllowed, type AnalysisIndex, type MetricView } from "@/lib/insights-view";
import { analysisHref, askHref, insightsDeckHref, insightsHref } from "@/lib/routes";

// ── ordering ────────────────────────────────────────────────────────────────────────────────

/** Status strength, strongest first. One order everywhere opportunities are listed. */
export const OPPORTUNITY_STATUS_ORDER: readonly OpportunityStatus[] = [
  "supported",
  "mixed_evidence",
  "emerging",
  "needs_research",
];

const statusRank = (status: OpportunityStatus): number => {
  const i = OPPORTUNITY_STATUS_ORDER.indexOf(status);
  return i < 0 ? OPPORTUNITY_STATUS_ORDER.length : i;
};

/** Opportunities by status strength; served order is kept within a status. Returns a new array. */
export function orderOpportunities(list: readonly Opportunity[]): Opportunity[] {
  return list
    .map((o, i) => ({ o, i }))
    .sort((a, b) => statusRank(a.o.status) - statusRank(b.o.status) || a.i - b.i)
    .map(({ o }) => o);
}

const INTEGRITY_RANK: Record<EvidenceRef["integrity"], number> = { verified: 0, stale: 1, withdrawn: 2 };

/** Strongest evidence first: verified passages, then changed ones, then withdrawn; curator order otherwise. */
export function orderEvidence(refs: readonly EvidenceRef[]): EvidenceRef[] {
  return refs
    .map((r, i) => ({ r, i }))
    .sort((a, b) => INTEGRITY_RANK[a.r.integrity] - INTEGRITY_RANK[b.r.integrity] || a.i - b.i)
    .map(({ r }) => r);
}

// ── lead signal ─────────────────────────────────────────────────────────────────────────────

export type LeadSignal =
  | { kind: "metric"; metric: MetricView }
  | { kind: "quote"; text: string; source: string }
  | { kind: "withheld" }
  | { kind: "none" };

/** A passage shortened to `max` characters at a word boundary, with an ellipsis when cut. */
export function shortQuote(text: string, max = 140): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max);
  const space = cut.lastIndexOf(" ");
  const head = (space > max / 2 ? cut.slice(0, space) : cut).replace(/[\s,;:.]+$/, "");
  return `${head}…`;
}

/**
 * The one signal a summary leads with: the first recomputed figure with a known base (else the
 * first recomputed figure), else the lead verified supporting passage. An item whose figures are
 * withheld and has no verified passage says so rather than showing nothing.
 */
export function leadSignal(opportunity: Opportunity, analyses: AnalysisIndex): LeadSignal {
  const visible = metricViews(opportunity, analyses).filter((m) => m.visible);
  const metric = visible.find((m) => m.base != null) ?? visible[0];
  if (metric) return { kind: "metric", metric };
  const lead = orderEvidence(opportunity.supporting).find((r) => r.integrity === "verified" && r.quote);
  if (lead?.quote) return { kind: "quote", text: shortQuote(lead.quote), source: lead.source.title };
  if (opportunity.metrics.length > 0 || !numbersAllowed(opportunity.integrity)) return { kind: "withheld" };
  return { kind: "none" };
}

// ── source mix and gaps ─────────────────────────────────────────────────────────────────────

const MIX_ORDER = ["customer", "competitor", "market", "internal", "financial"];
const MIX_LABEL: Record<string, string> = {
  customer: "Customer",
  competitor: "Competitor",
  market: "Market",
  internal: "Internal",
  financial: "Financial",
};

export interface SourceMixEntry {
  code: string;
  label: string;
  count: number;
}

/** Cited passages (supporting and contradicting) by source class, non-empty classes only, fixed order. */
export function sourceMix(opportunity: Pick<Opportunity, "supporting" | "contradicting">): SourceMixEntry[] {
  const counts = new Map<string, number>();
  for (const ref of [...opportunity.supporting, ...opportunity.contradicting]) {
    const code = ref.source.source_class || "other";
    counts.set(code, (counts.get(code) ?? 0) + 1);
  }
  const rank = (code: string) => {
    const i = MIX_ORDER.indexOf(code);
    return i < 0 ? MIX_ORDER.length : i;
  };
  return [...counts.entries()]
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
    .map(([code, count]) => ({ code, label: MIX_LABEL[code] ?? "Other", count }));
}

/** "No open gaps", "1 open gap", "2 open gaps". */
export function gapLabel(count: number): string {
  return count === 0 ? "No open gaps" : formatCount(count, "open gap");
}

// ── links ───────────────────────────────────────────────────────────────────────────────────

/** Chat with the composer prefilled with a research question (`?q=`). */
export function investigateHref(ws: string, question: string): string {
  return `${askHref(ws)}?q=${encodeURIComponent(question)}`;
}

/** The presentation deck preselected with this opportunity and its related insights and analyses. */
export function opportunityDeckHref(ws: string, opportunity: Pick<Opportunity, "id" | "related">): string {
  return insightsDeckHref(ws, {
    opportunities: [opportunity.id],
    signals: opportunity.related.signals,
    analyses: opportunity.related.analyses,
  });
}

export interface RelatedLink {
  id: string;
  title: string;
  href: string;
}

/** Related insights and analyses that exist in the brief, with their titles; unknown ids are skipped. */
export function relatedLinks(
  ws: string,
  opportunity: Pick<Opportunity, "related">,
  signals: readonly Pick<Signal, "id" | "title">[],
  analyses: AnalysisIndex,
): { insights: RelatedLink[]; analyses: RelatedLink[] } {
  const signalTitles = new Map(signals.map((s) => [s.id, s.title]));
  const insights = opportunity.related.signals.flatMap((id) => {
    const title = signalTitles.get(id);
    return title ? [{ id, title, href: `${insightsHref(ws)}#${encodeURIComponent(id)}` }] : [];
  });
  const linked = opportunity.related.analyses.flatMap((id) => {
    const analysis = analyses.get(id);
    return analysis ? [{ id, title: analysis.title, href: analysisHref(ws, id) }] : [];
  });
  return { insights, analyses: linked };
}

// ── comparable figures ──────────────────────────────────────────────────────────────────────

/** "Measure, group" -> measure and group; a label without a comma is a measure alone. */
export function splitMeasure(label: string): { measure: string; group: string | null } {
  const at = label.indexOf(", ");
  if (at < 0) return { measure: label, group: null };
  return { measure: label.slice(0, at).trim(), group: label.slice(at + 2).trim() || null };
}

/** A chart value label in the figure's own unit (percent values are already in percent units). */
export function formatMetricValue(unit: AnalysisUnit, value: number): string {
  if (unit === "percent") return `${value.toFixed(1)}%`;
  if (unit === "usd") return formatUsd(value);
  if (unit === "count") return formatNumber(value, 0);
  return formatNumber(value, 2);
}

export interface ComparableItem {
  group: string;
  value: number;
  view: MetricView;
}

export interface ComparableGroup {
  measure: string;
  unit: AnalysisUnit;
  items: ComparableItem[];
}

/**
 * Splits an opportunity's figures into groups that measure the same thing in the same unit for
 * different groups (charted together) and single figures. Derived figures and figures that were
 * not recomputed are never charted.
 */
export function comparableGroups(
  opportunity: Pick<Opportunity, "metrics" | "integrity">,
  analyses: AnalysisIndex,
): { groups: ComparableGroup[]; singles: MetricView[] } {
  const views = metricViews(opportunity, analyses);
  const keyOf = (i: number): string | null => {
    const metric = opportunity.metrics[i];
    const { measure, group } = splitMeasure(metric.label);
    if (!views[i].visible || metric.derived || metric.value == null || !group) return null;
    return `${metric.unit}|${measure}`;
  };
  const sizes = new Map<string, number>();
  views.forEach((_, i) => {
    const key = keyOf(i);
    if (key) sizes.set(key, (sizes.get(key) ?? 0) + 1);
  });

  const groups = new Map<string, ComparableGroup>();
  const singles: MetricView[] = [];
  views.forEach((view, i) => {
    const key = keyOf(i);
    const metric = opportunity.metrics[i];
    if (!key || (sizes.get(key) ?? 0) < 2 || metric.value == null) {
      singles.push(view);
      return;
    }
    const { measure, group } = splitMeasure(metric.label);
    const existing = groups.get(key) ?? { measure, unit: metric.unit, items: [] };
    groups.set(key, { ...existing, items: [...existing.items, { group: group ?? metric.label, value: metric.value, view }] });
  });
  return { groups: [...groups.values()], singles };
}
