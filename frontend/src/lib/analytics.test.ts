import { describe, expect, it } from "vitest";
import type { AnalyticsResult, MetricValue } from "./api/types";
import {
  buildResultTable,
  denominatorText,
  describeFilters,
  describeGrouping,
  describeMetrics,
  formatDifference,
  formatMetricValue,
} from "./analytics";

const metric = (over: Partial<MetricValue> = {}): MetricValue => ({
  key: "mean(nps)",
  fn: "mean",
  column: "nps",
  value: 41.25,
  exact: "41.25",
  unit: "number",
  scale: "",
  numerator: null,
  denominator: 296,
  ...over,
});

describe("formatMetricValue", () => {
  it.each([
    [{ unit: "percent", value: 38.2 }, "38.2%"],
    [{ unit: "percent", value: 40 }, "40.0%"],
    [{ unit: "count", value: 1234567 }, "1,234,567"],
    [{ unit: "currency_usd", scale: "billion", value: 15.1 }, "$15.1 billion"],
    [{ unit: "currency_usd", scale: "million", value: 612 }, "$612.0 million"],
    [{ unit: "currency_usd", scale: "thousand", value: 48.25 }, "$48.25 thousand"],
    [{ unit: "currency_usd", scale: "", value: 1234.5 }, "$1,234.50"],
    [{ unit: "rating", value: 4.12 }, "4.12"],
    [{ unit: "ratio", value: 0.382 }, "0.382"],
    [{ unit: "number", scale: "million", value: 3.4 }, "3.4 million"],
    [{ unit: "date", value: "2026-03-01" }, "2026-03-01"],
    [{ unit: "text", value: "<b>x</b>" }, "<b>x</b>"],
    [{ unit: "number", value: null }, "not computable"],
  ] as const)("formats %j as %s", (over, expected) => {
    expect(formatMetricValue(metric(over as Partial<MetricValue>))).toBe(expected);
  });

  it("ignores scale for percent and count", () => {
    expect(formatMetricValue(metric({ unit: "percent", scale: "million", value: 5.5 }))).toBe("5.5%");
  });
});

describe("formatDifference", () => {
  it("signs values and states percentage points for percent", () => {
    expect(formatDifference(metric({ unit: "percent", value: 4.2 }))).toBe("+4.2 pp");
    expect(formatDifference(metric({ unit: "percent", value: -4.2 }))).toBe("-4.2 pp");
    expect(formatDifference(metric({ unit: "number", value: 0 }))).toBe("0");
    expect(formatDifference(metric({ unit: "currency_usd", scale: "million", value: -1.5 }))).toBe("-$1.5 million");
    expect(formatDifference(metric({ value: null }))).toBe("not computable");
  });
});

describe("denominatorText", () => {
  it("renders share as numerator of denominator, others as n =", () => {
    expect(denominatorText(metric({ fn: "share", unit: "percent", numerator: 37, denominator: 296 }))).toBe(
      "37 of 296",
    );
    expect(denominatorText(metric())).toBe("n = 296");
    expect(denominatorText(metric({ denominator: 12345 }))).toBe("n = 12,345");
  });
});

describe("spec descriptions", () => {
  const spec = {
    filters: [
      { column: "region", op: "eq", operands: ["West"] },
      { column: "age_group", op: "in", operands: ["18-24", "25-34"] },
      { column: "nps", op: "between", operands: [5, 9] },
      { column: "gender", op: "is_null", operands: [] },
      { column: "nps", op: "gte", operands: [7] },
    ],
    group_by: ["region", "segment"],
    metrics: [
      { fn: "mean", column: "nps", key: "mean(nps)" },
      { fn: "share", column: "top_pain_point", key: "share(top_pain_point=delivery)", condition: { column: "top_pain_point", op: "eq", operands: ["delivery"] }, label: "Delivery share" },
    ],
  };

  it("describes filters in plain text", () => {
    expect(describeFilters(spec)).toEqual([
      "region = West",
      "age_group in 18-24, 25-34",
      "nps between 5 and 9",
      "gender is empty",
      "nps ≥ 7",
    ]);
  });

  it("describes grouping and metrics", () => {
    expect(describeGrouping(spec)).toEqual(["region", "segment"]);
    expect(describeMetrics(spec)).toEqual([
      "mean of nps",
      "share where top_pain_point = delivery",
    ]);
  });

  it("is defensive about malformed specs", () => {
    expect(describeFilters({ filters: "x" })).toEqual([]);
    expect(describeFilters({ filters: [null, 3, { column: 1 }] })).toEqual([]);
    expect(describeGrouping({})).toEqual([]);
    expect(describeMetrics({ metrics: [{}] })).toEqual([]);
  });
});

const base: AnalyticsResult = {
  result_id: "r1",
  workspace: "NORTHSTAR",
  dataset: "SURVEY-2026:1",
  source_code: "SURVEY-2026",
  source_version: 1,
  table: "Survey",
  operation: "aggregate",
  spec: {},
  rows: [],
  rows_scanned: 600,
  rows_matched: 296,
  rounding: "half_even",
  warnings: [],
};

describe("buildResultTable", () => {
  it("returns null for a single ungrouped row (shown as a metric list)", () => {
    const result = { ...base, rows: [{ group: {}, metrics: [metric()] }] };
    expect(buildResultTable(result)).toBeNull();
  });

  it("builds group columns + one column per metric", () => {
    const result: AnalyticsResult = {
      ...base,
      spec: { group_by: ["region"] },
      rows: [
        { group: { region: "West" }, metrics: [metric({ value: 40 })] },
        { group: { region: "East" }, metrics: [metric({ value: 35.5, denominator: 100 })] },
      ],
    };
    const table = buildResultTable(result);
    expect(table?.headers).toEqual(["region", "mean(nps)"]);
    expect(table?.rows.map((r) => r.cells.map((c) => c.text))).toEqual([
      ["West", "40"],
      ["East", "35.5"],
    ]);
    expect(table?.rows[1].cells[1].detail).toBe("n = 100");
  });

  it("builds A / B / difference rows for group_compare", () => {
    const pct = (value: number, denominator: number) =>
      metric({ key: "share(x)", fn: "share", unit: "percent", value, denominator, numerator: 10 });
    const result: AnalyticsResult = {
      ...base,
      operation: "group_compare",
      spec: { compare_column: "region", group_a: "West", group_b: "East" },
      rows: [
        { group: { region: "West" }, metrics: [pct(40, 100)] },
        { group: { region: "East" }, metrics: [pct(35, 120)] },
      ],
      difference: pct(5, 220),
    };
    const table = buildResultTable(result);
    expect(table?.headers).toEqual(["region", "share(x)"]);
    expect(table?.rows.map((r) => r.cells.map((c) => c.text))).toEqual([
      ["A: West", "40.0%"],
      ["B: East", "35.0%"],
      ["Difference (A − B)", "+5.0 pp"],
    ]);
  });

  it("lists filter_rows with a row link target", () => {
    const result: AnalyticsResult = {
      ...base,
      operation: "filter_rows",
      spec: { columns: ["region", "nps"] },
      rows: [
        { group: { region: "West", nps: 9 }, metrics: [], row_number: 185, handle: "NORTHSTAR/SURVEY-2026@v1:R185" },
        { group: { region: "East", nps: null }, metrics: [], row_number: 186, handle: null },
      ],
    };
    const table = buildResultTable(result);
    expect(table?.headers).toEqual(["Row", "region", "nps"]);
    expect(table?.rows[0].handle).toBe("NORTHSTAR/SURVEY-2026@v1:R185");
    expect(table?.rows[0].cells.map((c) => c.text)).toEqual(["Row 185", "West", "9"]);
    expect(table?.rows[1].handle).toBeNull();
    expect(table?.rows[1].cells.map((c) => c.text)).toEqual(["Row 186", "East", "-"]);
  });
});
