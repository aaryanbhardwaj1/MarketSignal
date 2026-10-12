/**
 * Plain-language description of a persisted computed result (`GET /analytics/results`). The
 * backend summary is a compact machine line such as
 * `aggregate ; sum(net_sales_usd) ; by month ; filters: channel eq Social Shop ; 24 of 120 rows`;
 * this turns it into "Total net sales (USD) by month" plus "Channel: Social Shop". Raw operation
 * names and metric keys never reach the business page.
 */
import type { AnalyticsResultSummary } from "@/lib/api/contracts";
import { humanizeKey, humanizeValue } from "./analysis-format";

const FN_WORDS: Record<string, string> = {
  sum: "Total",
  mean: "Average",
  median: "Median",
  min: "Lowest",
  max: "Highest",
  count_distinct: "Distinct",
};

const OPS: Record<string, string> = {
  eq: "",
  in: "",
  ne: "not ",
  not_in: "not ",
  gt: "more than ",
  gte: "at least ",
  lt: "less than ",
  lte: "at most ",
  between: "",
  contains: "contains ",
};

/** `sum(net_sales_usd)` -> "Total net sales (USD)"; `count(*)` -> "Number of records"; `share(a=b)` -> "Share with a: b". */
export function describeMetricKey(key: string): string {
  const m = /^([a-z_]+)\((.*)\)$/.exec(key.trim());
  if (!m) return humanizeKey(key.replace(/[^a-zA-Z0-9_]+/g, "_"));
  const [, fn, arg] = m;
  if (fn === "count") return arg === "*" || arg === "" ? "Number of records" : `Number of ${humanizeKey(arg).toLowerCase()} values`;
  if (fn === "share") {
    const cmp = /^(\w+)\s*(<=|>=|<|>)\s*(.+)$/.exec(arg);
    if (cmp) {
      const words: Record<string, string> = { "<=": "at most", ">=": "at least", "<": "less than", ">": "more than" };
      return `Share with ${lowerFirst(humanizeKey(cmp[1]))} ${words[cmp[2]]} ${humanizeValue(cmp[3])}`;
    }
    const [col, value] = arg.split("=");
    return value ? `Share with ${humanizeKey(col).toLowerCase()}: ${humanizeValue(value)}` : `Share of ${humanizeKey(col).toLowerCase()}`;
  }
  if (fn === "difference") return `Difference in ${lowerFirst(describeMetricKey(arg))}`;
  const word = FN_WORDS[fn];
  // "mean(avg_rating)" reads "Average rating", not "Average avg rating".
  const column = humanizeKey(word ? arg.replace(/^(avg|average|mean)_/, "") : arg);
  return word ? `${word} ${lowerFirst(column)}` : column;
}

/** Lower-cases a leading capital unless it starts an acronym ("YoY", "SKU", "NPS"). */
function lowerFirst(text: string): string {
  return /^[A-Z][a-z]*(\s|$|\()/.test(text) ? `${text.charAt(0).toLowerCase()}${text.slice(1)}` : text;
}

/** `channel eq Social Shop` -> "Channel: Social Shop"; `month between 2026-08-01, 2026-08-31` -> "Month: 2026-08-01 to 2026-08-31". */
export function describeFilterClause(clause: string): string {
  const nullCheck = /^(\S+)\s+(is_null|not_null)$/.exec(clause.trim());
  if (nullCheck) return `${humanizeKey(nullCheck[1])}: ${nullCheck[2] === "is_null" ? "not recorded" : "recorded"}`;
  const m = /^(\S+)\s+(eq|in|ne|not_in|gt|gte|lt|lte|between|contains)\s+(.*)$/.exec(clause.trim());
  if (!m) return clause.trim();
  const [, column, op, rest] = m;
  const values = rest.split(/,\s*/).map((v) => humanizeValue(v.trim()));
  const text = op === "between" && values.length === 2 ? `${values[0]} to ${values[1]}` : values.join(", ");
  return `${humanizeKey(column)}: ${OPS[op] ?? ""}${text}`;
}

function splitTopLevel(text: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let current = "";
  for (const ch of text) {
    if (ch === "(") depth += 1;
    if (ch === ")") depth = Math.max(0, depth - 1);
    if (ch === "," && depth === 0) {
      parts.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  if (current.trim()) parts.push(current.trim());
  return parts;
}

export interface ResultDescription {
  title: string;
  filters: string[];
  rowsMatched: string | null;
}

const KIND_TITLES: Record<AnalyticsResultSummary["tool"], string> = {
  aggregate: "Computed figures",
  filter_rows: "Matching records",
  group_compare: "Group comparison",
};

export function describeResult(result: Pick<AnalyticsResultSummary, "tool" | "summary" | "metrics">): ResultDescription {
  const parts = (result.summary ?? "").split(" ; ").map((p) => p.trim()).filter(Boolean);
  let metricKeys = [...result.metrics];
  let grouping: string | null = null;
  let comparison: string | null = null;
  let filters: string[] = [];
  let rowsMatched: string | null = null;
  for (const part of parts.slice(1)) {
    const rows = /^(\d+) of (\d+) rows$/.exec(part);
    if (rows) {
      rowsMatched = `${rows[1]} of ${rows[2]} rows`;
    } else if (part.startsWith("filters:")) {
      filters = part.slice("filters:".length).split(";").map(describeFilterClause).filter(Boolean);
    } else if (/^by \w+: A=/.test(part)) {
      const cmp = /^by \w+: A=(.+) vs B=(.+)$/.exec(part);
      comparison = cmp ? `${cmp[1].trim()} vs ${cmp[2].trim()}` : null;
    } else if (part.startsWith("by ")) {
      grouping = `by ${part.slice(3).split(/,\s*/).map((k) => humanizeKey(k).toLowerCase()).join(" and ")}`;
    } else if (part.includes("(") && metricKeys.length === 0) {
      metricKeys = splitTopLevel(part);
    }
  }
  const metricText = headlineMetrics(metricKeys).map(describeMetricKey).join(", ");
  const base = metricText || KIND_TITLES[result.tool] || "Computed result";
  const title = comparison ? `${base}: ${comparison}` : grouping ? `${base} ${grouping}` : base;
  return { title, filters, rowsMatched };
}

/** Drops supporting metrics (differences, record counts) when a more specific metric is present. */
function headlineMetrics(keys: readonly string[]): string[] {
  const unique = [...new Set(keys.map((k) => k.trim()))];
  const main = unique.filter((k) => !k.startsWith("difference(") && k !== "count(*)");
  return main.length > 0 ? main : unique.filter((k) => !k.startsWith("difference("));
}
