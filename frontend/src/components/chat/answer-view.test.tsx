import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { AnyCitationCard, CitationCard, ResultCitationCard } from "@/lib/api/types";
import { AnswerView } from "./answer-view";

const HANDLE = "NORTHSTAR/SURVEY-2026@v1:R185";
const CARD: CitationCard = {
  handle: HANDLE,
  source_code: "SURVEY-2026",
  source_title: "Consumer survey",
  source_class: "customer",
  source_type: "csv",
  locator_label: "Row 185",
  anchor_child_id: "0d4c7f8e-2b5a-4c1e-9a77-1f2e3d4c5b6a",
  char_start: 0,
  char_end: 4,
  parent_content_hash: null,
};

const render = (sections: unknown, content = "", citations: AnyCitationCard[] = [CARD]) =>
  renderToStaticMarkup(<AnswerView ws="NORTHSTAR" content={content} citations={citations} sections={sections} />);

describe("AnswerView", () => {
  it("renders evidence, inference and gap sections distinctly", () => {
    const html = render({
      answer: [`Running is up 12% [[${HANDLE}]].`, "Demand will likely keep rising [inference]."],
      findings: [`Gen Z leads adoption [[${HANDLE}]].`],
      interpretation: ["Brands should target campus events [inference]."],
      gaps: ["No pricing data was found."],
    });
    expect(html).toContain("Key findings");
    expect(html).toContain("Consumer survey · Row 185");
    expect(html).toContain("Inference");
    expect(html).not.toContain("[inference]");
    expect(html).toContain("Demand will likely keep rising.");
    expect(html).toContain("Gaps &amp; unknowns");
    expect(html).toContain("Unknown / evidence gap");
    expect(html).not.toContain(`[[${HANDLE}]]`);
  });

  it("shows the evidence-only banner and cards", () => {
    const html = render({
      evidence_only: [`**Consumer survey**, Row 185: “Gen Z runs more” [[${HANDLE}]]`],
      reason: "LLM_SYNTHESIS_UNAVAILABLE",
    });
    expect(html).toContain("No verified answer — showing the most relevant evidence");
    expect(html).toContain("Gen Z runs more");
    expect(html).toContain("Consumer survey · Row 185");
  });

  it("shows the abstention banner", () => {
    const html = render(
      { answer: ["No answer was generated."], gaps: ["No relevant evidence was found."], abstained: true },
      "",
      [],
    );
    expect(html).toContain("Insufficient evidence in this workspace");
    expect(html).toContain("No relevant evidence was found.");
  });

  it("falls back to the canonical content when sections are missing", () => {
    const html = render(null, `### Answer\n\nPlain answer [[${HANDLE}]].`);
    expect(html).toContain("<h3");
    expect(html).toContain("Plain answer");
    expect(html).toContain("Consumer survey · Row 185");
  });

  const RID = "3f2b7c9e-8a41-4d6b-b0a1-5c2d9e7f1a30";
  const RESULT: ResultCitationCard = {
    kind: "result",
    result_id: RID,
    source_code: "SURVEY-2026",
    dataset: "SURVEY-2026:1",
    source_version: 1,
    table: "Survey",
    op: "aggregate",
    summary: "mean(nps) by region",
    handle: "NORTHSTAR/SURVEY-2026@v1",
  };

  it("renders computed-result chips next to evidence chips without mixing them", () => {
    const html = render(
      { answer: [`West NPS is 41 [[result:${RID}]] and reviews agree [[${HANDLE}]].`] },
      "",
      [RESULT, CARD],
    );
    expect(html).toContain("computed");
    expect(html).toContain("mean(nps) by region");
    expect(html).toContain("Consumer survey · Row 185");
    expect(html).not.toContain("[[result:");
    expect(html).not.toContain(RID);
    // Only the evidence card is listed under Sources; the result card is not an evidence handle.
    expect(html).toContain("Sources (1)");
  });

  it("treats cards without a kind as evidence", () => {
    const html = render({ answer: [`Up [[${HANDLE}]].`] });
    expect(html).toContain("Consumer survey · Row 185");
  });

  it("styles answer_unknowns sentences in the Answer as gaps", () => {
    const html = render({
      answer: [`NPS is 41 [[result:${RID}]].`, "Churn by region is not available in the data."],
      answer_unknowns: ["Churn by region is not available in the data."],
    }, "", [RESULT]);
    expect(html.match(/Unknown \/ evidence gap/g)).toHaveLength(1);
    expect(html).toContain("Churn by region is not available in the data.");
  });

  it("renders result chips in the evidence-only fallback", () => {
    const html = render({ evidence_only: [`**Computed result** (SURVEY-2026:1): 41 [[result:${RID}]]`] }, "", [RESULT]);
    expect(html).toContain("No verified answer");
    expect(html).toContain("computed");
  });
});
