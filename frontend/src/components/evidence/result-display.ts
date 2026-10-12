/**
 * Business wording for a stored computed result (`GET /results/{id}`), shared by the result
 * drawer and every `ResultPanel` caller (Ask, Growth Opportunities). Column names and coded
 * values are humanized; dataset ids, operation names and rounding stay for "Technical details".
 * Everything here reshapes values the endpoint returned; nothing computes a new figure.
 */
import { buildResultTable, formatMetricValue, type ResultTableModel } from "@/lib/analytics";
import type { AnalyticsResult, MetricValue } from "@/lib/api/types";
import { formatNumber, humanizeColumn, humanizeValue, tableLabel } from "@/lib/format";
import { resultWarning } from "@/lib/labels";

type Spec = Record<string, unknown>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Lower-cases the first letter unless the word is an acronym ("Top pain point" -> "top pain point", "NPS" stays). */
function inline(text: string): string {
  return text.length > 1 && text.charAt(1) === text.charAt(1).toLowerCase()
    ? text.charAt(0).toLowerCase() + text.slice(1)
    : text;
}

function orList(values: string[]): string {
  if (values.length <= 1) return values.join("");
  return `${values.slice(0, -1).join(", ")} or ${values[values.length - 1]}`;
}

const COMPARISONS: Readonly<Record<string, (v: string) => string>> = {
  gt: (v) => `above ${v}`,
  gte: (v) => `${v} or more`,
  lt: (v) => `below ${v}`,
  lte: (v) => `${v} or less`,
};

/** One filter in plain words: "Top pain point: Knit upper durability", "Age group: 18-21 or 22-24". */
export function plainFilter(raw: unknown): string | null {
  if (!isRecord(raw) || typeof raw.column !== "string" || typeof raw.op !== "string") return null;
  const column = humanizeColumn(raw.column);
  const operands = (Array.isArray(raw.operands) ? raw.operands : []).map((v) => humanizeValue(v as string | number | null));
  switch (raw.op) {
    case "eq":
      return `${column}: ${operands[0] ?? "-"}`;
    case "ne":
      return `${column}: not ${operands[0] ?? "-"}`;
    case "in":
      return `${column}: ${orList(operands)}`;
    case "not_in":
      return `${column}: not ${orList(operands)}`;
    case "between":
      return `${column} between ${operands[0] ?? "-"} and ${operands[1] ?? "-"}`;
    case "is_null":
      return `${column} is empty`;
    case "not_null":
      return `${column} is recorded`;
    default: {
      const phrase = COMPARISONS[raw.op];
      return phrase ? `${column} ${phrase(operands[0] ?? "-")}` : `${column}: ${operands.join(", ")}`;
    }
  }
}

/** Filters of a normalized spec in plain words. */
export function plainFilters(spec: Spec): string[] {
  if (!Array.isArray(spec.filters)) return [];
  return spec.filters.map(plainFilter).filter((t): t is string => t !== null);
}

/** Grouping columns in plain words. */
export function plainGrouping(spec: Spec): string[] {
  if (!Array.isArray(spec.group_by)) return [];
  return spec.group_by.filter((g): g is string => typeof g === "string").map(humanizeColumn);
}

const FN_WORDS: Readonly<Record<string, string>> = {
  count_distinct: "Distinct",
  sum: "Total",
  mean: "Average",
  median: "Median",
  min: "Lowest",
  max: "Highest",
};

function plainMetric(raw: unknown): string | null {
  if (!isRecord(raw) || typeof raw.fn !== "string") return null;
  const column = typeof raw.column === "string" ? humanizeColumn(raw.column) : null;
  if (raw.fn === "share") {
    const condition = plainFilter(raw.condition);
    return condition ? `Share with ${inline(condition)}` : column ? `Share of ${inline(column)}` : "Share";
  }
  if (raw.fn === "count") return column ? `Records with ${inline(column)} recorded` : "Number of records";
  const word = FN_WORDS[raw.fn];
  return word && column ? `${word} ${inline(column)}` : column ?? "Computed figure";
}

/** The requested metric(s) in plain words ("Average satisfaction score", "Number of records"). */
export function plainMetrics(spec: Spec): string[] {
  const raw = Array.isArray(spec.metrics) ? spec.metrics : spec.metric !== undefined ? [spec.metric] : [];
  return raw.map(plainMetric).filter((t): t is string => t !== null);
}

/** The single headline metric of an ungrouped result, if there is exactly one. */
export function singleMetric(result: AnalyticsResult): MetricValue | null {
  if (buildResultTable(result) || result.rows.length !== 1) return null;
  return result.rows[0].metrics.length === 1 ? result.rows[0].metrics[0] : null;
}

/**
 * Base behind a figure, always with its denominator: "68 of 600 records" for a filtered count,
 * "37 of 296 records" for a share, "Based on 296 records" otherwise.
 */
export function resultBase(result: AnalyticsResult, metric: MetricValue): string {
  const scanned = formatNumber(result.rows_scanned);
  if (metric.fn === "count" && !metric.column) {
    return `${formatNumber(result.rows_matched)} of ${scanned} records`;
  }
  if (metric.fn === "share" && typeof metric.numerator === "number") {
    return `${formatNumber(metric.numerator)} of ${formatNumber(metric.denominator)} records`;
  }
  return `Based on ${formatNumber(metric.denominator)} of ${scanned} records`;
}

/** Title from what was computed and the filters: "Number of records where top pain point is knit upper durability". */
export function resultTitle(result: AnalyticsResult): string {
  const metrics = plainMetrics(result.spec);
  const head = metrics.length > 0 ? metrics.join("; ") : result.operation === "filter_rows" ? "Matching records" : "Computed figure";
  const filters = Array.isArray(result.spec.filters) ? result.spec.filters : [];
  const where = filters
    .map((f) => {
      if (!isRecord(f) || f.op !== "eq" || typeof f.column !== "string") return null;
      return `${inline(humanizeColumn(f.column))} is ${inline(humanizeValue(((f.operands as unknown[]) ?? [])[0] as string))}`;
    })
    .filter((t): t is string => t !== null);
  return where.length > 0 && where.length === filters.length ? `${head} where ${where.join(" and ")}` : head;
}

/** Calculation notes in plain words (unknown codes are left for "Technical details"). */
export function resultNotes(result: AnalyticsResult): string[] {
  return result.warnings.map(resultWarning).filter((w) => w.known).map((w) => w.label);
}

/** Table model with humanized column headers and coded cell values. */
export function plainResultTable(result: AnalyticsResult): ResultTableModel | null {
  const table = buildResultTable(result);
  if (!table) return null;
  return {
    headers: table.headers.map((h) => (/^[A-Za-z0-9_]+$/.test(h) ? humanizeColumn(h) : h)),
    rows: table.rows.map((row) => ({
      ...row,
      cells: row.cells.map((cell) => ({ ...cell, text: humanizeValue(cell.text) })),
    })),
  };
}

/** "Northstar Customer Survey 2026 · Version 1 · Survey responses", skipping a table that repeats the title. */
export function datasetLine(sourceTitle: string | null, version: number | string, table: string | null): string {
  const plainTable = table ? tableLabel(table) : "";
  const title = sourceTitle ?? "Workspace dataset";
  const showTable = plainTable && plainTable !== "-" && !title.toLowerCase().includes(plainTable.toLowerCase());
  return [title, `Version ${version}`, showTable ? plainTable : null].filter(Boolean).join(" · ");
}

/** Everything a `ResultPanel` needs for one stored result, in business language. */
export function describeResult(result: AnalyticsResult) {
  const single = singleMetric(result);
  return {
    title: resultTitle(result),
    value: single ? formatMetricValue(single) : undefined,
    base: single ? resultBase(result, single) : `${formatNumber(result.rows_matched)} of ${formatNumber(result.rows_scanned)} records matched`,
    filters: plainFilters(result.spec),
    groupBy: plainGrouping(result.spec),
    notes: resultNotes(result),
  };
}
