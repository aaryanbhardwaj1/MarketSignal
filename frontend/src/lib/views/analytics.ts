/**
 * View logic for the Analytics pages ("What does the data show?"). Everything here groups,
 * selects or labels values the analyses endpoint returned; nothing computes a new figure.
 */
import type { Analysis, AnalysisFilter, AnalysisRow, AnalysisUnit, BusinessArea } from "@/lib/api/contracts";
import { describeFilter, listingRowLabel, rowLabel, baseNoun } from "@/components/analytics/analysis-format";
import { formatNumber, formatUsd, humanizeColumn, humanizeValue } from "@/lib/format";
import { askHref, insightsDeckHref, type DeckSelection } from "@/lib/routes";

/** Reading order of business areas: customer problems first, growth last. */
export const BUSINESS_AREA_ORDER: readonly BusinessArea[] = [
  "Customer friction",
  "Customer satisfaction",
  "Willingness to pay",
  "Product performance",
  "Channels and growth",
];

export const OTHER_AREA = "Other analyses";

export interface AreaGroup {
  area: string;
  analyses: Analysis[];
}

/** Analyses grouped by business area, in reading order; areas with no analyses are left out. */
export function groupByArea(analyses: readonly Analysis[]): AreaGroup[] {
  const known = BUSINESS_AREA_ORDER.map((area) => ({ area: area as string, analyses: analyses.filter((a) => a.business_area === area) }));
  const other = analyses.filter((a) => !a.business_area || !BUSINESS_AREA_ORDER.includes(a.business_area));
  return [...known, { area: OTHER_AREA, analyses: other }].filter((g) => g.analyses.length > 0);
}

export type ChartKind = "withheld" | "empty" | "single" | "line" | "hbar" | "grouped" | "table";

/** Colours available for series in a grouped chart (matches the chart palette). */
const MAX_SERIES = 4;

const TEMPORAL_KEY = /(^|_)(period|quarter|month|year|week|date|day)(_|$)/;

/** True for grouping keys that order results in time ("period", "fiscal_quarter", "month"). */
export function isTemporalKey(key: string): boolean {
  return TEMPORAL_KEY.test(key.toLowerCase());
}

function distinct(rows: readonly AnalysisRow[], key: string): string[] {
  return [...new Set(rows.map((r) => r.group[key] ?? ""))];
}

/** The best way to show one analysis's result. Numbers are withheld unless it was recomputed. */
export function chooseChart(analysis: Analysis): ChartKind {
  if (analysis.status !== "computed") return "withheld";
  if (analysis.presentation === "single" && analysis.display) return "single";
  if (analysis.rows.length === 0) return analysis.display ? "single" : "empty";
  if (analysis.op === "filter_rows") return "table";
  const keys = analysis.group_by;
  if (keys.length === 1 && isTemporalKey(keys[0]) && analysis.rows.length >= 2) return "line";
  if (keys.length === 1) return "hbar";
  if (keys.length === 2) return groupedSeries(analysis) ? "grouped" : "table";
  return "table";
}

/** A value in the analysis unit, worded as the engine formats its own displays. */
export function formatUnitValue(value: number, unit: AnalysisUnit): string {
  if (!Number.isFinite(value)) return "-";
  switch (unit) {
    case "percent":
      return `${value.toFixed(1)}%`;
    case "usd":
      return formatUsd(value, { digits: Number.isInteger(value) ? 0 : 2 });
    case "score":
    case "ratio":
      return value.toFixed(2);
    default:
      return formatNumber(value);
  }
}

/** Formats chart values: the endpoint's own display for a row value, the unit wording otherwise (axis ticks; dollars compact). */
export function valueFormatter(analysis: Pick<Analysis, "rows" | "unit">): (value: number) => string {
  const displays = new Map<number, string>();
  for (const r of analysis.rows) if (r.value != null && r.display) displays.set(r.value, r.display);
  return (value) => displays.get(value) ?? (analysis.unit === "usd" ? compactUsd(value) : formatUnitValue(value, analysis.unit));
}

/** Short dollar ticks for chart axes ("$2.0M", "$500K"); exact below a thousand. */
export function compactUsd(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `$${(value / 1e3).toFixed(0)}K`;
  return formatUnitValue(value, "usd");
}

export interface Bar {
  label: string;
  value: number;
  emphasis: boolean;
}

function ranked(items: readonly { label: string; value: number }[], n: number): Bar[] {
  return [...items]
    .sort((a, b) => b.value - a.value)
    .slice(0, n)
    .map((item, i) => ({ ...item, emphasis: i === 0 }));
}

/** The `n` largest groups of a grouped analysis, largest first; only the leader is emphasised. */
export function topBars(analysis: Analysis, n = 5): Bar[] {
  if (analysis.status !== "computed") return [];
  const items = analysis.rows
    .filter((r): r is AnalysisRow & { value: number } => r.value != null)
    .map((r) => ({ label: rowLabel(r, analysis.group_by), value: r.value }));
  return ranked(items, n);
}

function isNumericCell(value: string | undefined): boolean {
  return value != null && value.trim() !== "" && Number.isFinite(Number(value));
}

export interface ListingMeasure {
  column: string;
  label: string;
}

/** The column a listing is about: its first numeric column ("return_rate_pct"). */
export function listingMeasure(analysis: Pick<Analysis, "columns" | "rows">): ListingMeasure | null {
  const columns = analysis.columns ?? [];
  const column = columns.find((c) => analysis.rows.length > 0 && analysis.rows.every((r) => isNumericCell(r.group[c])));
  return column ? { column, label: humanizeColumn(column) } : null;
}

/** A listing row's name: a "...name" column when there is one, else its text cells. */
function listingName(row: AnalysisRow, columns: readonly string[]): string {
  const nameCol = columns.find((c) => /name/.test(c) && row.group[c]);
  return nameCol ? row.group[nameCol] : listingRowLabel(row, columns);
}

/** Top rows of a listing by its measure column, for a compact bar chart. */
export function listingBars(analysis: Analysis, n = 5): { measure: ListingMeasure | null; bars: Bar[] } {
  const measure = listingMeasure(analysis);
  if (!measure || analysis.status !== "computed") return { measure, bars: [] };
  const columns = analysis.columns ?? [];
  const items = analysis.rows.map((r) => ({ label: listingName(r, columns), value: Number(r.group[measure.column]) }));
  return { measure, bars: ranked(items, n) };
}

export interface GroupedSeries {
  categoryKey: string;
  seriesKey: string;
  categories: string[];
  series: { name: string; values: number[] }[];
}

/**
 * Two-way grouping as a grouped bar chart: the dimension with fewer values becomes the series
 * (ties: the first grouping key). Null when the series would exceed the chart palette.
 */
export function groupedSeries(analysis: Analysis): GroupedSeries | null {
  if (analysis.group_by.length !== 2) return null;
  const [a, b] = analysis.group_by;
  const seriesKey = distinct(analysis.rows, b).length < distinct(analysis.rows, a).length ? b : a;
  const categoryKey = seriesKey === a ? b : a;
  const seriesValues = distinct(analysis.rows, seriesKey);
  const categoryValues = distinct(analysis.rows, categoryKey);
  if (seriesValues.length > MAX_SERIES || seriesValues.length === 0) return null;
  const cell = (s: string, c: string) =>
    analysis.rows.find((r) => r.group[seriesKey] === s && r.group[categoryKey] === c)?.value ?? Number.NaN;
  return {
    categoryKey,
    seriesKey,
    categories: categoryValues.map((c) => humanizeValue(c)),
    series: seriesValues.map((s) => ({ name: humanizeValue(s), values: categoryValues.map((c) => cell(s, c)) })),
  };
}

/** A time-ordered analysis as one line, in the endpoint's row order. */
export function lineSeries(analysis: Analysis): { x: string[]; values: number[] } | null {
  const key = analysis.group_by[0];
  if (!key) return null;
  const rows = analysis.rows.filter((r): r is AnalysisRow & { value: number } => r.value != null);
  return { x: rows.map((r) => humanizeValue(r.group[key])), values: rows.map((r) => r.value) };
}

/** Age bands the survey reports as its Gen Z cohort ("Gen Z (18-27)"). */
const GEN_Z_RANGE = "18-27";

/** Contiguous numeric bands ("18-21", "22-24", "25-27") as one range ("18-27"), else null. */
function bandRange(values: readonly (string | number)[]): string | null {
  const bands = values.map((v) => /^(\d+)-(\d+)$/.exec(String(v)));
  if (bands.length < 2 || bands.some((m) => !m)) return null;
  const spans = bands.map((m) => [Number(m![1]), Number(m![2])] as const).sort((x, y) => x[0] - y[0]);
  const contiguous = spans.every((s, i) => i === 0 || s[0] === spans[i - 1][1] + 1);
  return contiguous ? `${spans[0][0]}-${spans[spans.length - 1][1]}` : null;
}

/** A filter as a readable chip: "Age group: Gen Z (18-27)", "Quarter: Q3 2026". */
export function filterChipLabel(filter: AnalysisFilter): string {
  if (filter.op === "in" || filter.op === "eq") {
    const range = bandRange(filter.values);
    if (range) {
      const label = filter.label || humanizeColumn(filter.column);
      return `${label}: ${range === GEN_Z_RANGE ? `Gen Z (${range})` : range}`;
    }
  }
  return describeFilter(filter);
}

export function filterChips(analysis: Pick<Analysis, "filters">): string[] {
  return analysis.filters.map(filterChipLabel);
}

/** Who or what the analysis covers: "400 Gen Z respondents", "600 respondents", "30 return records". */
export function populationLine(analysis: Analysis): string | null {
  if (analysis.denominator) return `${formatNumber(analysis.denominator.value)} ${analysis.denominator.label}`;
  const matched = analysis.provenance.rows_matched;
  return matched != null ? `${formatNumber(matched)} ${baseNoun(analysis)}` : null;
}

export type TextView = { kind: "shown"; text: string } | { kind: "withheld" } | { kind: "absent" };

/** The plain-language takeaway; withheld when its numbers no longer match the computed result. */
export function summaryView(analysis: Pick<Analysis, "summary" | "summary_status" | "status">): TextView {
  if (analysis.summary && analysis.summary_status === "verified" && analysis.status === "computed") return { kind: "shown", text: analysis.summary };
  return analysis.summary_status === "absent" ? { kind: "absent" } : { kind: "withheld" };
}

/**
 * The curated interpretation (always an inference). Withheld when the result's numbers are
 * withheld, or when the endpoint marks it unverified (`interpretation_status`, when present).
 */
export function interpretationView(analysis: Analysis): TextView {
  const status = (analysis as Analysis & { interpretation_status?: string }).interpretation_status;
  if (status && status !== "verified") return status === "absent" ? { kind: "absent" } : { kind: "withheld" };
  if (!analysis.interpretation) return { kind: "absent" };
  if (analysis.status !== "computed") return { kind: "withheld" };
  return { kind: "shown", text: analysis.interpretation.text };
}

/** Deck selection URL for one analysis plus the insights that use it (shared `insightsDeckHref` encoding). */
export function analysisDeckHref(ws: string, selection: DeckSelection): string {
  return insightsDeckHref(ws, selection);
}

/** Ask with the analysis question pre-filled. */
export function followUpHref(ws: string, question: string): string {
  return `${askHref(ws)}?${new URLSearchParams({ q: question }).toString()}`;
}
