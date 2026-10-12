import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ResultCitationCard } from "@/lib/api/types";
import { CitationChip } from "./citation-chip";

const RID = "3f2b7c9e-8a41-4d6b-b0a1-5c2d9e7f1a30";
const ref: ResultCitationCard = {
  kind: "result",
  result_id: RID,
  source_code: "SURVEY-2026",
  dataset: "SURVEY-2026:1",
  op: "aggregate",
  summary: "aggregate ; mean(nps) ; by region ; 296 of 600 rows",
};

describe("result chip", () => {
  it("outside a workspace page is plain text in business words, distinct from evidence chips", () => {
    const html = renderToStaticMarkup(<CitationChip ws="NORTHSTAR" token={{ kind: "result", resultId: RID, ref }} />);
    expect(html).not.toContain("<button");
    expect(html).toContain("Computed figure: Average NPS by region");
    expect(html).not.toMatch(/mean\(nps\)|aggregate ;/);
    expect(html).not.toContain("href=");
    expect(html).not.toContain('role="dialog"');
  });

  it("still renders when no card is known", () => {
    const html = renderToStaticMarkup(<CitationChip ws="NORTHSTAR" token={{ kind: "result", resultId: RID, ref: null }} />);
    expect(html).toContain("Computed figure");
  });
});
