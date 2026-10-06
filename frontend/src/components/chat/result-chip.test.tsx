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
  summary: "mean(nps) by region",
};

describe("result chip", () => {
  it("is a closed button labelled as computed, distinct from evidence chips", () => {
    const html = renderToStaticMarkup(<CitationChip ws="NORTHSTAR" token={{ kind: "result", resultId: RID, ref }} />);
    expect(html).toContain("<button");
    expect(html).toContain("computed");
    expect(html).toContain("mean(nps) by region");
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain("href=");
    expect(html).not.toContain('role="dialog"');
  });

  it("still renders when no card is known", () => {
    const html = renderToStaticMarkup(<CitationChip ws="NORTHSTAR" token={{ kind: "result", resultId: RID, ref: null }} />);
    expect(html).toContain("computed");
  });
});
