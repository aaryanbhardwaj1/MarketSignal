/**
 * View helpers for the Insights page ("What does the evidence mean?"). Pure functions over the
 * curated brief (E9), so grouping, counts, the figure shown on each card, forecast attribution
 * and deck links are unit-tested. Numbers follow `lib/insights-view`: only recomputed figures,
 * never for an item that could not be re-verified.
 */
import type { EvidenceRef, InsightsBrief, Signal, SignalKind, SignalStatus } from "@/lib/api/contracts";
import { metricViews, type AnalysisIndex, type MetricView } from "@/lib/insights-view";
import { DECK_PARAM, analysisHref, insightsHref, opportunityHref, type DeckSelection } from "@/lib/routes";

// ── categories ─────────────────────────────────────────────────────────────────────────────

export type InsightCategoryId = "opportunities" | SignalKind;

export interface InsightCategory {
  id: InsightCategoryId;
  label: string;
  /** One line under the section title: what this category is for. */
  description: string;
}

export const INSIGHT_CATEGORIES: readonly InsightCategory[] = [
  {
    id: "opportunities",
    label: "Strategic Opportunities",
    description: "Growth directions the evidence points to. Full detail lives in Growth Opportunities.",
  },
  { id: "emerging_signal", label: "Emerging Signals", description: "Shifts in behaviour that are starting to show." },
  { id: "risk_blocker", label: "Risks / Blockers", description: "What could slow or stop growth." },
  { id: "competitor_finding", label: "Competitor Findings", description: "How competitors are positioned." },
  { id: "optimization", label: "Optimization Opportunities", description: "Friction the business could reduce now." },
  {
    id: "future_outlook",
    label: "Future Outlook",
    description: "Forward-looking statements. Forecasts are stated by a cited source; everything else is a hypothesis.",
  },
];

const SIGNAL_KINDS: readonly SignalKind[] = [
  "emerging_signal",
  "risk_blocker",
  "competitor_finding",
  "optimization",
  "future_outlook",
];

export function categoryLabel(id: InsightCategoryId): string {
  return INSIGHT_CATEGORIES.find((c) => c.id === id)?.label ?? id;
}

export interface SignalGroups {
  byKind: Record<SignalKind, Signal[]>;
  /** v1 items without a kind: shown separately, never forced into a category. */
  unclassified: Signal[];
}

export function groupSignals(signals: readonly Signal[]): SignalGroups {
  const byKind = Object.fromEntries(
    SIGNAL_KINDS.map((kind) => [kind, signals.filter((s) => s.kind === kind)]),
  ) as Record<SignalKind, Signal[]>;
  return { byKind, unclassified: signals.filter((s) => s.kind == null) };
}

export function categoryCounts(brief: Pick<InsightsBrief, "signals" | "opportunities">): Record<InsightCategoryId, number> {
  const { byKind } = groupSignals(brief.signals);
  return {
    opportunities: brief.opportunities.length,
    ...(Object.fromEntries(SIGNAL_KINDS.map((k) => [k, byKind[k].length])) as Record<SignalKind, number>),
  };
}

// ── summary band ───────────────────────────────────────────────────────────────────────────

const STATUS_ORDER: readonly { status: SignalStatus; label: string }[] = [
  { status: "strong_evidence", label: "Strong evidence" },
  { status: "emerging", label: "Emerging" },
  { status: "mixed_evidence", label: "Mixed evidence" },
  { status: "needs_validation", label: "Needs validation" },
];

export interface StatusCount {
  status: SignalStatus;
  label: string;
  count: number;
}

/** Insight statuses in a fixed order; zero counts are omitted so nothing is padded. */
export function statusCounts(signals: readonly Signal[]): StatusCount[] {
  return STATUS_ORDER.map((s) => ({ ...s, count: signals.filter((x) => x.status === s.status).length })).filter(
    (s) => s.count > 0,
  );
}

export interface EvidenceTotals {
  supporting: number;
  contradicting: number;
  /** Findings with at least one verified contradicting passage. */
  withContradictions: number;
}

export function evidenceTotals(signals: readonly Signal[]): EvidenceTotals {
  return {
    supporting: signals.reduce((n, s) => n + s.support_count, 0),
    contradicting: signals.reduce((n, s) => n + s.contradiction_count, 0),
    withContradictions: signals.filter((s) => s.contradiction_count > 0).length,
  };
}

// ── card content ───────────────────────────────────────────────────────────────────────────

/**
 * The one figure a card shows: the first recomputed figure with a known base (so it reads
 * "27.0% of 400 Gen Z respondents"), else the first recomputed figure, else none. Null for an
 * item that could not be re-verified.
 */
export function strongestMetric(
  signal: Pick<Signal, "metrics" | "integrity">,
  analyses: AnalysisIndex,
): MetricView | null {
  const visible = metricViews(signal, analyses).filter((m) => m.visible);
  return visible.find((m) => m.base != null) ?? visible[0] ?? null;
}

export interface OutlookNature {
  type: "forecast" | "hypothesis";
  /** Titles of the sources whose passages state the projection (forecasts only). */
  sources: string[];
}

/**
 * Whether a forward-looking finding is a forecast (a cited, still-available passage states the
 * projection) or a hypothesis. Never a forecast without a source to attribute it to.
 */
export function outlookNature(signal: Pick<Signal, "evidence">): OutlookNature {
  const stating = signal.evidence.filter((e) => e.states_projection && e.integrity !== "withdrawn");
  if (stating.length === 0) return { type: "hypothesis", sources: [] };
  return { type: "forecast", sources: [...new Set(stating.map((e) => e.source.title))] };
}

export interface SourceChip {
  code: string;
  title: string;
  /** The first cited passage from this source; opened in the evidence drawer. */
  ref: EvidenceRef;
  available: boolean;
}

/** Each cited source once, in citation order. */
export function uniqueSources(signal: Pick<Signal, "evidence">): SourceChip[] {
  const seen = new Map<string, SourceChip>();
  for (const ref of signal.evidence) {
    const prior = seen.get(ref.source.code);
    if (!prior) {
      seen.set(ref.source.code, { code: ref.source.code, title: ref.source.title, ref, available: ref.integrity !== "withdrawn" });
    } else if (!prior.available && ref.integrity !== "withdrawn") {
      seen.set(ref.source.code, { ...prior, ref, available: true });
    }
  }
  return [...seen.values()];
}

export interface RelatedLink {
  kind: "analysis" | "opportunity" | "insight";
  id: string;
  label: string;
  href: string;
}

/** Titled links to the analyses, opportunities and other insights a finding relates to. */
export function relatedLinks(
  ws: string,
  signal: Pick<Signal, "related">,
  brief: Pick<InsightsBrief, "signals" | "opportunities">,
  analyses: AnalysisIndex,
): RelatedLink[] {
  const analysisLinks = signal.related.analyses.map((id): RelatedLink => ({
    kind: "analysis",
    id,
    label: analyses.get(id)?.title ?? "Related analysis",
    href: analysisHref(ws, id),
  }));
  const opportunityLinks = signal.related.opportunities.map((id): RelatedLink => ({
    kind: "opportunity",
    id,
    label: brief.opportunities.find((o) => o.id === id)?.title ?? "Related opportunity",
    href: opportunityHref(ws, id),
  }));
  const insightLinks = signal.related.signals.map((id): RelatedLink => ({
    kind: "insight",
    id,
    label: brief.signals.find((s) => s.id === id)?.title ?? "Related insight",
    href: `${insightsHref(ws)}#${encodeURIComponent(id)}`,
  }));
  return [...opportunityLinks, ...analysisLinks, ...insightLinks];
}

// ── deck selection ─────────────────────────────────────────────────────────────────────────

/** Selection keys: `s:<signalId>` for insights, `o:<opportunityId>` for opportunities. */
export const signalKey = (id: string): string => `s:${id}`;
export const opportunityKey = (id: string): string => `o:${id}`;

export interface ResolvedDeckSelection {
  signals: string[];
  opportunities: string[];
  analyses: string[];
}

/**
 * What "Create presentation" sends to the deck builder: the selected findings in brief order,
 * or every strategic opportunity when nothing is selected.
 */
export function deckSelectionFor(
  brief: Pick<InsightsBrief, "signals" | "opportunities">,
  selected: ReadonlySet<string>,
): ResolvedDeckSelection {
  if (selected.size === 0) {
    return { signals: [], opportunities: brief.opportunities.map((o) => o.id), analyses: [] };
  }
  return {
    signals: brief.signals.filter((s) => selected.has(signalKey(s.id))).map((s) => s.id),
    opportunities: brief.opportunities.filter((o) => selected.has(opportunityKey(o.id))).map((o) => o.id),
    analyses: [],
  };
}

/** Reads a deck selection back from the deck URL (`?s=a,b&o=O1&a=x`); ids may not contain commas. */
export function parseDeckSelection(params: Pick<URLSearchParams, "get">): ResolvedDeckSelection {
  const read = (key: keyof DeckSelection): string[] => [
    ...new Set((params.get(DECK_PARAM[key]) ?? "").split(",").filter((id) => id.length > 0)),
  ];
  return { signals: read("signals"), opportunities: read("opportunities"), analyses: read("analyses") };
}

// ── copy ───────────────────────────────────────────────────────────────────────────────────

/** "Northstar" -> "Northstar's"; "Northstar Athletics" -> "Northstar Athletics'". */
export function possessive(name: string): string {
  return /s$/i.test(name) ? `${name}'` : `${name}'s`;
}
