import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AnalyticsResult, MetricValue } from "@/lib/api/types";
import { ResultCardView } from "./result-card";

const metric = (over: Partial<MetricValue> = {}): MetricValue => ({
  key: "share(top_pain_point=delivery_speed)",
  fn: "share",
  column: "top_pain_point",
  value: 38.2,
  exact: "38.1756756",
  unit: "percent",
  scale: "",
  numerator: 113,
  denominator: 296,
  ...over,
});

const base: AnalyticsResult = {
  result_id: "3f2b7c9e-8a41-4d6b-b0a1-5c2d9e7f1a30",
  workspace: "NORTHSTAR",
  dataset: "SURVEY-2026:1",
  source_code: "SURVEY-2026",
  source_version: 1,
  table: "Survey",
  operation: "aggregate",
  spec: {
    filters: [{ column: "region", op: "eq", operands: ["West"] }],
    group_by: [],
    metrics: [{ fn: "share", column: "top_pain_point", key: "share(...)", condition: { column: "top_pain_point", op: "eq", operands: ["delivery_speed"] } }],
  },
  rows: [{ group: {}, metrics: [metric()] }],
  rows_scanned: 600,
  rows_matched: 296,
  rounding: "half_even; percent 1dp; currency 2dp",
  warnings: ["NULLS_EXCLUDED"],
};

const render = (result: AnalyticsResult) => renderToStaticMarkup(<ResultCardView ws="NORTHSTAR" result={result} />);

describe("ResultCardView", () => {
  it("labels the result as a deterministic calculation, not a source", () => {
    expect(render(base)).toContain("Computed result — deterministic calculation, not a quoted source");
  });

  it("shows value, unit, denominator, filters and provenance for a single metric", () => {
    const html = render(base);
    expect(html).toContain("38.2%");
    expect(html).toContain("113 of 296");
    expect(html).toContain("region = West");
    expect(html).toContain("SURVEY-2026:1");
    expect(html).toContain("SURVEY-2026");
    expect(html).toContain("v1");
    expect(html).toContain("half_even; percent 1dp; currency 2dp");
    expect(html).toContain("296 of 600");
    expect(html).toContain("NULLS EXCLUDED");
  });

  it("states scaled currency in words", () => {
    const html = render({
      ...base,
      rows: [{ group: {}, metrics: [metric({ key: "sum(value_usd_bn)", fn: "sum", unit: "currency_usd", scale: "billion", value: 15.1, numerator: null })] }],
    });
    expect(html).toContain("$15.1 billion");
    expect(html).toContain("n = 296");
  });

  it("renders a grouped table", () => {
    const html = render({
      ...base,
      spec: { group_by: ["region"], filters: [] },
      rows: [
        { group: { region: "West" }, metrics: [metric({ value: 40 })] },
        { group: { region: "East" }, metrics: [metric({ value: 35.5 })] },
      ],
    });
    expect(html).toContain("<table");
    expect(html).toContain("Grouped by");
    expect(html).toContain("West");
    expect(html).toContain("35.5%");
    expect(html).toContain("No filters");
  });

  it("renders group_compare with the difference", () => {
    const html = render({
      ...base,
      operation: "group_compare",
      spec: { compare_column: "region", group_a: "West", group_b: "East", filters: [] },
      rows: [
        { group: { region: "West" }, metrics: [metric({ value: 40 })] },
        { group: { region: "East" }, metrics: [metric({ value: 35 })] },
      ],
      difference: metric({ value: 5, denominator: 592 }),
    });
    expect(html).toContain("A: West");
    expect(html).toContain("B: East");
    expect(html).toContain("Difference (A − B)");
    expect(html).toContain("+5.0 pp");
  });

  it("links filter_rows handles to the evidence viewer", () => {
    const handle = "NORTHSTAR/SURVEY-2026@v1:R185";
    const html = render({
      ...base,
      operation: "filter_rows",
      spec: { columns: ["region"], filters: [] },
      rows: [{ group: { region: "West" }, metrics: [], row_number: 185, handle }],
    });
    expect(html).toContain(`href="/w/NORTHSTAR/evidence?h=${encodeURIComponent(handle)}"`);
    expect(html).toContain("Row 185");
  });

  it("renders hostile values as escaped text", () => {
    const html = render({
      ...base,
      operation: "filter_rows",
      spec: { columns: ["verbatim"], filters: [{ column: "verbatim", op: "eq", operands: ["<img src=x onerror=alert(1)>"] }] },
      rows: [{ group: { verbatim: "**bold** <script>x</script> [[result:abc]]" }, metrics: [], row_number: 1, handle: null }],
    });
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("<strong>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("**bold**");
  });

  it("explains an empty selection", () => {
    const html = render({ ...base, rows: [], rows_matched: 0, warnings: ["EMPTY_SELECTION"] });
    expect(html).toContain("EMPTY SELECTION");
  });
});
