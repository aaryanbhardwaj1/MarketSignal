/**
 * Plain-text formatting of computed (analytics) results. Every function returns strings that the
 * UI renders as text nodes only: values, column names and filter operands come from documents and
 * are never interpreted as Markdown or HTML.
 *
 * Column names, metric keys and categorical values are worded with the shared humanizers
 * (`humanizeColumn` / `humanizeValue` in lib/format.ts) and the Analytics page's
 * `describeMetricKey` / `describeFilterClause`, so one computed result reads the same in Ask, the result drawer and
 * Analytics. Raw spec keys stay in the result's Technical details.
 */
import { describeFilterClause, describeMetricKey } from "./result-summary";
import type { AnalyticsResult, AnalyticsScale, MetricValue, ResultRow } from "./api/types";
import { humanizeColumn, humanizeValue } from "./format";

const NOT_COMPUTABLE = "not computable";
const EMPTY_CELL = "-";
const MAX_FRACTION_DIGITS = 6;

const SCALE_WORDS: Readonly<Record<string, string>> = {
  thousand: "thousand",
  million: "million",
  billion: "billion",
};

type Scalar = string | number | boolean | null | undefined;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function decimal(value: number, minFraction: number): string {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: minFraction,
    maximumFractionDigits: Math.max(minFraction, MAX_FRACTION_DIGITS),
  });
}

function scaleWord(unit: MetricValue["unit"], scale: AnalyticsScale | undefined): string {
  if (unit === "percent" || unit === "count" || unit === "date" || unit === "text") return "";
  return (scale && SCALE_WORDS[scale]) || "";
}

/** Magnitude of a numeric value with its unit and scale, without any sign. */
function formatMagnitude(value: number, unit: MetricValue["unit"], scale: AnalyticsScale | undefined): string {
  const word = scaleWord(unit, scale);
  const suffix = word ? ` ${word}` : "";
  switch (unit) {
    case "percent":
      return `${decimal(value, 1)}%`;
    case "currency_usd":
      return `$${decimal(value, word ? 1 : 2)}${suffix}`;
    case "count":
      return decimal(value, 0);
    default:
      return `${decimal(value, 0)}${suffix}`;
  }
}

/** The rounded value as stated in answers, e.g. "38.2%", "$15.1 billion", "1,234". */
export function formatMetricValue(metric: Pick<MetricValue, "value" | "unit" | "scale">): string {
  const { value, unit, scale } = metric;
  if (value === null || value === undefined) return NOT_COMPUTABLE;
  if (typeof value === "string") return value;
  if (!Number.isFinite(value)) return NOT_COMPUTABLE;
  return formatMagnitude(value, unit, scale);
}

/** A group_compare difference (A - B): explicitly signed; percent is stated in points. */
export function formatDifference(metric: Pick<MetricValue, "value" | "unit" | "scale">): string {
  const { value, unit, scale } = metric;
  if (typeof value !== "number" || !Number.isFinite(value)) return formatMetricValue(metric);
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (unit === "percent") return `${sign}${decimal(abs, 1)} pp`;
  return `${sign}${formatMagnitude(abs, unit, scale)}`;
}

/** "37 of 296" for a share, "n = 296" otherwise. */
export function denominatorText(metric: Pick<MetricValue, "fn" | "numerator" | "denominator">): string {
  const denominator = decimal(metric.denominator, 0);
  if (metric.fn === "share" && typeof metric.numerator === "number") {
    return `${decimal(metric.numerator, 0)} of ${denominator}`;
  }
  return `n = ${denominator}`;
}

function scalarText(value: unknown): string {
  if (value === null || value === undefined) return "empty";
  return String(value);
}

const COMPARATOR_SYMBOLS: Readonly<Record<string, string>> = { gt: ">", gte: ">=", lt: "<", lte: "<=" };

interface FilterSpec {
  column: string;
  op: string;
  operands: unknown[];
}

function filterSpec(raw: unknown): FilterSpec | null {
  if (!isRecord(raw) || typeof raw.column !== "string" || typeof raw.op !== "string") return null;
  return { column: raw.column, op: raw.op, operands: Array.isArray(raw.operands) ? raw.operands : [] };
}

/** "Region: West", "Age group: 18-24, 25-34", "NPS: at least 7" (the Analytics page wording). */
function describeFilter(raw: unknown): string | null {
  const f = filterSpec(raw);
  if (!f) return null;
  if (f.op === "is_null" || f.op === "not_null") return describeFilterClause(`${f.column} ${f.op}`);
  return describeFilterClause(`${f.column} ${f.op} ${f.operands.map(scalarText).join(", ")}`);
}

/** Plain-text filters from a normalized spec, e.g. "Region: West". */
export function describeFilters(spec: Record<string, unknown>): string[] {
  if (!Array.isArray(spec.filters)) return [];
  return spec.filters.map(describeFilter).filter((text): text is string => text !== null);
}

/** Grouping columns in plain words, e.g. "Age group". */
export function describeGrouping(spec: Record<string, unknown>): string[] {
  if (!Array.isArray(spec.group_by)) return [];
  return spec.group_by.filter((g): g is string => typeof g === "string").map(humanizeColumn);
}

function describeShare(condition: unknown, column: string | null): string {
  const f = filterSpec(condition);
  if (!f) return describeMetricKey(column ? `share(${column})` : "share()");
  const first = scalarText(f.operands[0]);
  if (f.op === "eq") return describeMetricKey(`share(${f.column}=${first})`);
  const symbol = COMPARATOR_SYMBOLS[f.op];
  if (symbol) return describeMetricKey(`share(${f.column}${symbol}${first})`);
  const clause = describeFilter(condition);
  return clause ? `Share with ${clause.charAt(0).toLowerCase()}${clause.slice(1)}` : "Share";
}

function describeMetric(raw: unknown): string | null {
  if (!isRecord(raw) || typeof raw.fn !== "string") return null;
  const column = typeof raw.column === "string" ? raw.column : null;
  if (raw.fn === "share") return describeShare(raw.condition, column);
  return describeMetricKey(`${raw.fn}(${column ?? "*"})`);
}

/** The metric(s) requested (aggregate: `metrics`, group_compare: `metric`), e.g. "Average NPS". */
export function describeMetrics(spec: Record<string, unknown>): string[] {
  const raw = Array.isArray(spec.metrics) ? spec.metrics : spec.metric !== undefined ? [spec.metric] : [];
  return raw.map(describeMetric).filter((text): text is string => text !== null);
}

const SNAKE_TOKEN = /\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g;

/**
 * Raw dataset codes (snake_case columns and categorical values) named by the cited results'
 * summaries, mapped to plain words: `knit_upper_durability` -> "knit upper durability". Used to
 * clean answer prose that quotes a dataset value verbatim; only codes the results name are mapped.
 */
export function datasetTerms(summaries: readonly string[]): ReadonlyMap<string, string> {
  const terms = new Map<string, string>();
  for (const summary of summaries) {
    for (const match of summary.matchAll(SNAKE_TOKEN)) {
      const token = match[0];
      const end = (match.index ?? 0) + token.length;
      if (summary[end] === "(") continue; // a function name such as count_distinct(...)
      terms.set(token, token.replace(/_/g, " "));
    }
  }
  return terms;
}

/** Replaces known dataset codes in prose, leaving citation markers (`[...]`) untouched. */
export function humanizeDatasetTerms(text: string, terms: ReadonlyMap<string, string>): string {
  if (terms.size === 0) return text;
  return text
    .split(/(\[[^\]]*\])/)
    .map((part) => (part.startsWith("[") ? part : part.replace(SNAKE_TOKEN, (token) => terms.get(token) ?? token)))
    .join("");
}

export interface TableCell {
  text: string;
  /** Secondary text, e.g. the denominator behind a metric. */
  detail?: string;
}

export interface TableRow {
  cells: TableCell[];
  /** Evidence handle of a listed row (filter_rows), linkable to the evidence viewer. */
  handle: string | null;
  emphasis?: "difference";
}

export interface ResultTableModel {
  headers: string[];
  rows: TableRow[];
}

function cellText(value: Scalar): string {
  if (value === null || value === undefined || value === "") return EMPTY_CELL;
  return typeof value === "string" ? humanizeValue(value) : String(value);
}

function metricCell(metric: MetricValue, difference = false): TableCell {
  return {
    text: difference ? formatDifference(metric) : formatMetricValue(metric),
    detail: denominatorText(metric),
  };
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

function groupColumns(result: AnalyticsResult): string[] {
  const fromSpec = stringList(result.spec.group_by);
  if (fromSpec.length > 0) return fromSpec;
  const seen: string[] = [];
  for (const row of result.rows) {
    for (const key of Object.keys(row.group ?? {})) if (!seen.includes(key)) seen.push(key);
  }
  return seen;
}

function compareTable(result: AnalyticsResult): ResultTableModel {
  const column = typeof result.spec.compare_column === "string" ? result.spec.compare_column : null;
  const first = result.rows[0]?.metrics[0];
  const headers = [column ? humanizeColumn(column) : "Group", first ? describeMetricKey(first.key) : "Value"];
  const rows: TableRow[] = result.rows.map((row, i) => {
    const label = column ? row.group[column] : Object.values(row.group ?? {})[0];
    const metric = row.metrics[0];
    return {
      cells: [{ text: `${i === 0 ? "A" : "B"}: ${cellText(label)}` }, metric ? metricCell(metric) : { text: EMPTY_CELL }],
      handle: null,
    };
  });
  if (result.difference) {
    rows.push({
      cells: [{ text: "Difference (A − B)" }, metricCell(result.difference, true)],
      handle: null,
      emphasis: "difference",
    });
  }
  return { headers, rows };
}

function listingTable(result: AnalyticsResult): ResultTableModel {
  const fromSpec = stringList(result.spec.columns);
  const columns = fromSpec.length > 0 ? fromSpec : Object.keys(result.rows[0]?.group ?? {});
  const rows = result.rows.map((row: ResultRow, i) => ({
    cells: [
      { text: `Row ${row.row_number ?? i + 1}` },
      ...columns.map((c) => ({ text: cellText(row.group?.[c]) })),
    ],
    handle: row.handle ?? null,
  }));
  return { headers: ["Row", ...columns.map(humanizeColumn)], rows };
}

function groupedTable(result: AnalyticsResult): ResultTableModel {
  const groups = groupColumns(result);
  const keys = (result.rows[0]?.metrics ?? []).map((m) => m.key);
  const rows = result.rows.map((row) => ({
    cells: [
      ...groups.map((g) => ({ text: cellText(row.group?.[g]) })),
      ...keys.map((_, i) => (row.metrics[i] ? metricCell(row.metrics[i]) : { text: EMPTY_CELL })),
    ],
    handle: null,
  }));
  return { headers: [...groups.map(humanizeColumn), ...keys.map(describeMetricKey)], rows };
}

/**
 * Table model for grouped aggregates, group_compare (A, B, difference) and filter_rows listings.
 * Returns null when the result is a plain list of metrics (one ungrouped row) or has no rows.
 */
export function buildResultTable(result: AnalyticsResult): ResultTableModel | null {
  if (result.rows.length === 0) return null;
  if (result.operation === "group_compare") return compareTable(result);
  if (result.operation === "filter_rows") return listingTable(result);
  if (groupColumns(result).length === 0 && result.rows.length === 1) return null;
  return groupedTable(result);
}
