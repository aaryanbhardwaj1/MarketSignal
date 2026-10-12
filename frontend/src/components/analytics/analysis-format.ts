/**
 * Business wording for named analyses (`GET /analytics/analyses`). Everything here reshapes or
 * labels values the endpoint returned; nothing computes a new figure.
 */
import type { Analysis, AnalysisFilter, AnalysisRow, AnalysisUnit } from "@/lib/api/contracts";
import { formatNumber, formatPercent, formatUsd, humanizeColumn, humanizeValue } from "@/lib/format";
import { aggregationFn, basisKind, describeBasis } from "@/lib/insights-view";

function sentenceCase(text: string): string {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

function joinOr(values: string[]): string {
  if (values.length <= 1) return values.join("");
  return `${values.slice(0, -1).join(", ")} or ${values[values.length - 1]}`;
}

const OP_WORDS: Record<string, string> = {
  ne: "not",
  not_in: "not",
  gt: "more than",
  gte: "at least",
  lt: "less than",
  lte: "at most",
  contains: "contains",
};

/** "Age group: 18-21, 22-24 or 25-27", "Quarter: Q3 2026", "Rating: at least 4". */
export function describeFilter(filter: AnalysisFilter): string {
  const label = filter.label || humanizeColumn(filter.column);
  const values = filter.values.map((v) => humanizeValue(v));
  if (filter.op === "between" && values.length === 2) return `${label}: ${values[0]} to ${values[1]}`;
  const prefix = OP_WORDS[filter.op];
  return `${label}: ${prefix ? `${prefix} ` : ""}${joinOr(values)}`;
}

/** One wording per unit across Analytics (analysis value columns and dataset column units). */
export const UNIT_LABELS: Record<AnalysisUnit, string> = {
  percent: "Percent",
  count: "Count",
  usd: "US dollars",
  score: "Average score",
  ratio: "Ratio",
};

const COLUMN_UNIT_LABELS: Record<string, string> = {
  ...UNIT_LABELS,
  currency_usd: UNIT_LABELS.usd,
  number: "Number",
  rating: "Rating",
  date: "Date",
  text: "-",
};

/** Unit of a dataset column, in the same words as analysis units ("Percent", "US dollars"). */
export function columnUnitLabel(unit: string | null | undefined): string {
  if (!unit) return "-";
  return COLUMN_UNIT_LABELS[unit] ?? humanizeColumn(unit);
}

export function unitLabel(unit: AnalysisUnit): string {
  return UNIT_LABELS[unit] ?? sentenceCase(unit);
}

const CATEGORY_LABELS: Record<string, string> = {
  customer: "Customer",
  product: "Product",
  channel: "Channel",
  pricing: "Pricing",
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? humanizeColumn(category);
}

function isNumeric(value: string): boolean {
  return value.trim() !== "" && Number.isFinite(Number(value));
}

/** Label for one result row from its group values (all of them for grouped aggregates). */
export function rowLabel(row: AnalysisRow, keys?: readonly string[]): string {
  const order = keys && keys.length > 0 ? keys : Object.keys(row.group);
  return order
    .map((k) => row.group[k])
    .filter((v): v is string => typeof v === "string" && v !== "")
    .map((v) => humanizeValue(v))
    .join(" · ");
}

/** For listings (`filter_rows`): the non-numeric cells identify the row ("NS-KR2 · Knit Runner 2"). */
export function listingRowLabel(row: AnalysisRow, columns: readonly string[]): string {
  return columns
    .map((c) => row.group[c])
    .filter((v): v is string => typeof v === "string" && v !== "" && !isNumeric(v))
    .join(" · ");
}

/**
 * What a row's base counts when the endpoint gives no label: survey groupings (cohort, segment)
 * count respondents; anything else counts records.
 */
export function baseNoun(analysis: Pick<Analysis, "denominator" | "group_by">): string {
  if (analysis.denominator) return analysis.denominator.label;
  return analysis.group_by.some((k) => k === "cohort" || k === "segment") ? "respondents" : "records";
}

/** True when a count row counts records (its base is itself), so it can be read as a share of the population. */
function isRecordCount(row: AnalysisRow, analysis: Pick<Analysis, "unit" | "spec">): boolean {
  if (analysis.unit !== "count") return false;
  const fn = aggregationFn(analysis);
  if (fn) return fn === "count";
  return row.denominator != null && row.denominator === row.value;
}

/**
 * Base behind one row, in the shared wording (see `describeBasis`):
 * "108 of 400 respondents" (shares), "of 400 Gen Z respondents" (record counts),
 * "Total across 7 of 30 return records" (sums), "Average of 96 of 600 respondents" (means).
 */
export function rowBase(
  row: AnalysisRow,
  analysis: Pick<Analysis, "denominator" | "unit" | "spec" | "group_by">,
): string | null {
  if (row.denominator == null) return null;
  const noun = baseNoun(analysis);
  if (row.numerator != null) return `${formatNumber(row.numerator)} of ${formatNumber(row.denominator)} ${noun}`;
  if (isRecordCount(row, analysis)) {
    const share = recordShare(row, analysis);
    return share && analysis.denominator ? `${share} of ${formatNumber(analysis.denominator.value)} ${noun}` : null;
  }
  const kind = basisKind(analysis.unit, aggregationFn(analysis));
  return describeBasis(kind, row.denominator, noun, analysis.denominator?.value ?? null)?.text ?? null;
}

/**
 * The share a record count represents of the analysis population (108 of 400 -> "27.0%"), or null
 * when the analysis has no population base. Reshapes two endpoint values; no new data.
 */
export function recordShare(row: AnalysisRow, analysis: Pick<Analysis, "denominator" | "unit" | "spec">): string | null {
  if (!analysis.denominator || analysis.denominator.value <= 0 || row.value == null) return null;
  if (!isRecordCount(row, analysis)) return null;
  return formatPercent(row.value / analysis.denominator.value, { digits: 1 });
}

/** Card footer: the population the analysis covers, in plain words. */
export function coverageLine(analysis: Analysis): string | null {
  const noun = baseNoun(analysis);
  if (analysis.denominator) return `Based on ${formatNumber(analysis.denominator.value)} ${noun}`;
  const matched = analysis.provenance.rows_matched;
  return matched != null ? `Based on ${formatNumber(matched)} ${noun}` : null;
}

/** A listing cell, formatted by its column suffix; text is shown as given. */
export function formatListingCell(column: string, raw: string | undefined): string {
  if (raw == null || raw === "") return "-";
  if (!isNumeric(raw)) return raw;
  const n = Number(raw);
  if (column.endsWith("_pct")) return `${n.toFixed(1)}%`;
  if (column.endsWith("_usd")) return formatUsd(n, { digits: Number.isInteger(n) ? 0 : 2 });
  return formatNumber(n);
}

export interface Headline {
  /** What the figure describes ("Fit inconsistency"). */
  label: string;
  display: string;
  /** Base or denominator ("108 of 400 Gen Z respondents"), when the endpoint gives one. */
  context: string | null;
}

/**
 * The figure a card leads with: the single value when there is one, otherwise the first row as the
 * endpoint ordered it. Null unless the analysis was recomputed and matched (numbers are withheld otherwise).
 */
export function analysisHeadline(analysis: Analysis): Headline | null {
  if (analysis.status !== "computed") return null;
  if (analysis.value != null && analysis.display) {
    return {
      label: analysis.title,
      display: analysis.display,
      context: analysis.denominator ? `Based on ${formatNumber(analysis.denominator.value)} ${analysis.denominator.label}` : null,
    };
  }
  const first = analysis.rows[0];
  if (!first || first.display == null) return null;
  const label =
    analysis.op === "filter_rows" && analysis.columns
      ? listingRowLabel(first, analysis.columns)
      : rowLabel(first, analysis.group_by);
  const share = recordShare(first, analysis);
  // A count of respondents leads with its share of the population; the count becomes the base.
  if (share) return { label, display: share, context: `${first.display} of ${formatNumber(analysis.denominator?.value ?? 0)} ${baseNoun(analysis)}` };
  return { label, display: first.display, context: rowBase(first, analysis) };
}

export interface AnalysisState {
  kind: "computed" | "mismatch" | "unavailable";
  label: string;
  tone: "success" | "warn" | "neutral";
  message: string | null;
}

export function analysisState(analysis: Pick<Analysis, "status">): AnalysisState {
  switch (analysis.status) {
    case "computed":
      return { kind: "computed", label: "Recomputed", tone: "success", message: null };
    case "mismatch":
      return {
        kind: "mismatch",
        label: "Numbers withheld",
        tone: "warn",
        message: "Result changed since curation; numbers withheld until the analysis is reviewed.",
      };
    default:
      return {
        kind: "unavailable",
        label: "Unavailable",
        tone: "neutral",
        message: "This dataset is not currently available, so the analysis could not be recomputed.",
      };
  }
}

/** Plain-language scope line: filters, then the dataset ("Age group: 18-21, 22-24 or 25-27 · Northstar Customer Survey 2026"). */
export function scopeLine(analysis: Pick<Analysis, "filters" | "provenance">): string {
  return [...analysis.filters.map(describeFilter), analysis.provenance.source_title].join(" · ");
}

/** A listing column is numeric when every non-empty cell parses as a number. */
export function isNumericColumn(rows: readonly AnalysisRow[], column: string): boolean {
  const cells = rows.map((r) => r.group[column]).filter((v): v is string => typeof v === "string" && v !== "");
  return cells.length > 0 && cells.every(isNumeric);
}
