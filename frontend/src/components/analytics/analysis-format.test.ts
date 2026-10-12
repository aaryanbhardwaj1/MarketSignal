import { describe, expect, it } from "vitest";
import analysesFixture from "@/lib/api/__fixtures__/insights-analyses.json";
import type { AnalysesResponse, Analysis } from "@/lib/api/contracts";
import { analysisHeadline, describeFilter, formatListingCell, humanizeKey, humanizeValue, rowBase } from "./analysis-format";
import { describeMetricKey, describeResult } from "./result-summary";

const analyses = (analysesFixture as unknown as AnalysesResponse).analyses;

describe("analysis wording", () => {
  it("humanizes keys and values", () => {
    expect(humanizeKey("return_rate_pct")).toBe("Return rate (%)");
    expect(humanizeKey("aov_usd")).toBe("Average order value (USD)");
    expect(humanizeValue("2026-09")).toBe("September 2026");
    expect(humanizeValue("2026-Q3")).toBe("Q3 2026");
    expect(humanizeValue("fit_inconsistency")).toBe("Fit inconsistency");
    expect(humanizeValue("Social Shop")).toBe("Social Shop");
  });

  it("describes filters in plain language", () => {
    expect(describeFilter({ column: "age_group", label: "Age group", op: "in", values: ["18-21", "22-24", "25-27"] })).toBe(
      "Age group: 18-21, 22-24 or 25-27",
    );
    expect(describeFilter({ column: "rating", label: "", op: "gte", values: [4] })).toBe("Rating: at least 4");
    expect(describeFilter({ column: "month", label: "Month", op: "between", values: ["2026-07", "2026-09"] })).toBe(
      "Month: July 2026 to September 2026",
    );
  });

  it("formats listing cells by column suffix", () => {
    expect(formatListingCell("return_rate_pct", "12.5")).toBe("12.5%");
    expect(formatListingCell("sku", "NS-KR2")).toBe("NS-KR2");
    expect(formatListingCell("x", undefined)).toBe("-");
  });

  it("gives each row its own base when present", () => {
    expect(rowBase({ group: {}, value: 0.27, numerator: 108, denominator: 400, display: "27.0%" }, { denominator: null })).toBe("108 of 400");
    expect(rowBase({ group: {}, value: 3, display: "3" }, { denominator: null })).toBeNull();
  });

  it("only returns a headline for computed analyses", () => {
    for (const a of analyses) {
      const withheld: Analysis = { ...a, status: "mismatch" };
      expect(analysisHeadline(withheld)).toBeNull();
      if (a.status === "computed" && a.rows.length > 0) expect(analysisHeadline(a)?.display).toBeTruthy();
    }
  });
});

describe("saved result descriptions", () => {
  it("turns metric keys into business wording", () => {
    expect(describeMetricKey("sum(net_sales_usd)")).toBe("Total net sales (USD)");
    expect(describeMetricKey("count(*)")).toBe("Number of records");
    expect(describeMetricKey("share(pain_point=fit_inconsistency)")).toBe("Share with pain point: Fit inconsistency");
  });

  it("describes a persisted summary without operation names", () => {
    const d = describeResult({
      tool: "aggregate",
      summary: "aggregate ; sum(net_sales_usd) ; by month ; filters: channel eq Social Shop ; 24 of 120 rows",
      metrics: ["sum(net_sales_usd)"],
    });
    expect(d).toEqual({ title: "Total net sales (USD) by month", filters: ["Channel: Social Shop"], rowsMatched: "24 of 120 rows" });
  });

  it("names listings and comparisons without raw tool names", () => {
    const listing = describeResult({ tool: "filter_rows", summary: "filter_rows ; filters: generation eq Gen Z; year eq 2026 ; 3 of 54 rows", metrics: [] });
    expect(listing.title).toBe("Matching records");
    expect(listing.filters).toEqual(["Generation: Gen Z", "Year: 2026"]);
    const compare = describeResult({ tool: "group_compare", summary: null, metrics: [] });
    expect(compare.title).toBe("Group comparison");
  });

  it("handles comparisons, threshold shares, null checks and acronyms", () => {
    expect(
      describeResult({
        tool: "group_compare",
        summary: "group_compare ; difference(mean(conversion_rate_pct)), mean(conversion_rate_pct) ; by segment: A=Gen Z vs B=Millennial ; filters: channel eq Social Shop ; 24 of 120 rows",
        metrics: [],
      }),
    ).toEqual({ title: "Average conversion rate (%): Gen Z vs Millennial", filters: ["Channel: Social Shop"], rowsMatched: "24 of 120 rows" });
    expect(describeMetricKey("share(rating<=2)")).toBe("Share with rating at most 2");
    expect(describeMetricKey("mean(avg_rating)")).toBe("Average rating");
    expect(describeMetricKey("mean(yoy_change_pct)")).toBe("Average YoY change (%)");
    expect(describeResult({ tool: "aggregate", summary: "aggregate ; count(*) ; filters: yoy_growth_pct is_null ; 9 of 54 rows", metrics: ["count(*)"] }).filters).toEqual([
      "YoY growth (%): not recorded",
    ]);
    expect(describeResult({ tool: "aggregate", summary: null, metrics: ["mean(rating)", "count(*)"] }).title).toBe("Average rating");
  });
});
