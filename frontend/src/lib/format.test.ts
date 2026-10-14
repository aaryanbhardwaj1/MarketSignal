import { describe, expect, it } from "vitest";
import {
  businessLocator,
  formatBytes,
  formatCount,
  formatMs,
  formatNumber,
  formatPercent,
  formatRelativeDate,
  formatUsd,
  humanize,
  humanizeColumn,
  humanizeValue,
  parseRowPassage,
  splitWorkspaceName,
  tableLabel,
} from "./format";

describe("format", () => {
  it("returns '-' for missing or non-finite values instead of 0", () => {
    for (const fn of [formatNumber, formatPercent, formatUsd, formatMs, formatBytes]) {
      expect(fn(null)).toBe("-");
      expect(fn(undefined)).toBe("-");
      expect(fn(Number.NaN)).toBe("-");
    }
  });

  it("formats numbers with grouping and sensible decimals", () => {
    expect(formatNumber(12480)).toBe("12,480");
    expect(formatNumber(3.14159)).toBe("3.14");
    expect(formatNumber(0.8125, 3)).toBe("0.813");
  });

  it("formats percents from ratios by default, or from percent units", () => {
    expect(formatPercent(0.4236)).toBe("42.4%");
    expect(formatPercent(42.36, { ratio: false, digits: 0 })).toBe("42%");
  });

  it("formats USD, keeping sub-cent precision for estimates", () => {
    expect(formatUsd(1234.5)).toBe("$1,234.50");
    expect(formatUsd(0.0042)).toBe("$0.0042");
    expect(formatUsd(0)).toBe("$0.00");
  });

  it("keeps the existing ms, bytes, hash and humanize behaviour", () => {
    expect(formatMs(840)).toBe("840 ms");
    expect(formatMs(1234)).toBe("1.23 s");
    expect(formatMs(12_345)).toBe("12.3 s");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(humanize("ready_degraded")).toBe("ready degraded");
  });

  it("formats relative dates against an injectable clock", () => {
    const now = new Date("2026-10-12T12:00:00Z");
    expect(formatRelativeDate("2026-10-12T11:59:30Z", now)).toBe("just now");
    expect(formatRelativeDate("2026-10-12T09:00:00Z", now)).toBe("3 hours ago");
    expect(formatRelativeDate("2026-10-11T12:00:00Z", now)).toBe("yesterday");
    expect(formatRelativeDate("2026-09-28T12:00:00Z", now)).toBe("2 weeks ago");
    expect(formatRelativeDate(null, now)).toBe("-");
    expect(formatRelativeDate("not a date", now)).toBe("not a date");
  });

  it("counts with the right noun form and grouping", () => {
    expect(formatCount(1, "source")).toBe("1 source");
    expect(formatCount(12480, "passage")).toBe("12,480 passages");
    expect(formatCount(2, "analysis", "analyses")).toBe("2 analyses");
  });

  it("humanizes columns, values and table names, keeping acronyms", () => {
    expect(humanizeColumn("top_pain_point")).toBe("Top pain point");
    expect(humanizeColumn("return_rate_pct")).toBe("Return rate (%)");
    expect(humanizeColumn("nps_score")).toBe("NPS score");
    expect(humanizeColumn("total_sku_returns")).toBe("Total SKU returns");
    expect(humanizeValue("knit_upper_durability")).toBe("Knit upper durability");
    expect(humanizeValue("2026-09")).toBe("September 2026");
    expect(humanizeValue("2026-Q3")).toBe("Q3 2026");
    expect(humanizeValue("West")).toBe("West");
    expect(humanizeValue(1421)).toBe("1,421");
    expect(humanizeValue(null)).toBe("-");
    expect(tableLabel("SKU_Performance")).toBe("SKU performance");
    expect(tableLabel("PnL_Summary")).toBe("P&L summary");
  });

  it("keeps only business parts of an evidence locator", () => {
    expect(businessLocator("Page 4, Block 2")).toBe("Page 4");
    expect(businessLocator("Section 1, Block 6")).toBe("Section 1");
    expect(businessLocator("Sheet 'Returns', Row 12")).toBe("Returns sheet, Row 12");
    expect(businessLocator("Sheet 'Market_Sizing'")).toBe("Market sizing sheet");
    expect(businessLocator("Sheet 'SKU_Performance', Row 7")).toBe("SKU performance sheet, Row 7");
    expect(businessLocator("Sheet 'Plan, 2026', Row 3")).toBe("Plan 2026 sheet, Row 3");
    expect(businessLocator("Sheet 3, Row 2")).toBe("Sheet 3, Row 2");
    expect(businessLocator("Slide 14, Block 3")).toBe("Slide 14");
    expect(businessLocator("Computed result 12")).toBe("Computed result 12");
    expect(businessLocator("Block 6")).toBe("Passage 6");
    expect(businessLocator(null)).toBe("");
  });

  it("parses spreadsheet and CSV passages into labelled fields, and leaves prose alone", () => {
    expect(
      parseRowPassage("reason: Fit - runs small; total_sku_returns: 1421; returns_count: 583; share_of_sku_returns_pct: 41"),
    ).toMatchObject([
      { label: "Reason", value: "Fit - runs small", start: 8, end: 24 },
      { label: "Total SKU returns", value: "1,421" },
      { label: "Returns count", value: "583" },
      { label: "Share of SKU returns", value: "41%" },
    ]);
    expect(parseRowPassage("Gen Z shoppers said fit varies; most returns cite sizing.")).toBeNull();
    expect(parseRowPassage("single: value")).toBeNull();
    expect(parseRowPassage("line one: a\nline two: b")).toBeNull();
  });

  it("splits a workspace name into the company and the engagement", () => {
    expect(splitWorkspaceName("Northstar Athletics - Gen Z Growth Engagement")).toEqual({
      name: "Northstar Athletics",
      detail: "Gen Z Growth Engagement",
    });
    expect(splitWorkspaceName("Acme")).toEqual({ name: "Acme", detail: null });
  });
});
