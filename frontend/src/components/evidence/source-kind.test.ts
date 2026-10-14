import { describe, expect, it } from "vitest";
import { sourceKind } from "./source-kind";

describe("sourceKind", () => {
  it.each([
    ["Northstar Customer Survey 2026", "csv", "customer", "Survey"],
    ["Northstar Customer Interviews", "docx", "customer", "Interview transcript"],
    ["Northstar FY27 Planning Memo", "markdown", "internal", "Strategy memo"],
    ["Northstar Q3 Strategy Review", "pptx", "internal", "Strategy review"],
    ["Kinetic Lab Annual Report 2025 (excerpt)", "pdf", "competitor", "Competitor filing"],
    ["Pace & Co. Investor Update", "pptx", "competitor", "Competitor filing"],
    ["Northstar Product Performance", "xlsx", "internal", "Spreadsheet"],
    ["Northstar Product Reviews", "csv", "customer", "Customer reviews"],
    ["Untitled upload", "xlsx", null, "Spreadsheet"],
    ["Untitled upload", "pdf", null, "PDF"],
    ["Untitled upload", "weird", null, "Source"],
  ])("%s (%s) → %s", (title, type, cls, expected) => {
    expect(sourceKind({ title, source_type: type, source_class: cls })).toBe(expected);
  });
});
