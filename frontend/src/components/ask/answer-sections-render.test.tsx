import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { CitationCard } from "@/lib/api/types";
import { AnswerView } from "./answer-view";

const card = (code: string, row: number): CitationCard => ({
  handle: `NORTHSTAR/${code}@v1:R${row}`,
  source_code: code,
  source_title: `${code} title`,
  source_class: "customer",
  source_type: "csv",
  locator_label: `Row ${row}`,
  anchor_child_id: null,
  char_start: null,
  char_end: null,
  parent_content_hash: null,
});
const A = card("SURVEY", 1);
const B = card("REVIEWS", 2);

const render = (sections: unknown, nextSteps?: string) =>
  renderToStaticMarkup(
    <QueryClientProvider client={new QueryClient()}>
      <AnswerView ws="NORTHSTAR" content="" citations={[A, B]} sections={sections} nextSteps={nextSteps} />
    </QueryClientProvider>,
  );

const headings = (html: string) => [...html.matchAll(/<h3[^>]*>([^<]+)/g)].map((m) => m[1]);

describe("AnswerView section order", () => {
  it("renders sections in the fixed order", () => {
    const html = render(
      {
        answer: [`Answer text [[${B.handle}]].`],
        findings: [`A finding [[${A.handle}]].`],
        conflicts: [`A conflict [[${A.handle}]].`],
        gaps: ["Nothing on pricing."],
      },
      "Next",
    );
    expect(headings(html)).toEqual([
      "Executive answer",
      "Key findings",
      "Supporting evidence",
      "Conflicting evidence",
      "Evidence gaps",
      "Recommended next step",
      "Sources",
    ]);
  });

  it("hides empty sections", () => {
    const html = render({ answer: [`Only an answer [[${A.handle}]].`] });
    expect(headings(html)).toEqual(["Executive answer", "Supporting evidence", "Sources"]);
    expect(html).not.toContain("Risks");
    expect(html).not.toContain("Key findings");
    expect(html).not.toContain("Conflicting evidence");
    expect(html).not.toContain("Evidence gaps");
    expect(html).not.toContain("Analytics");
  });

  it("numbers supporting evidence by first inline citation", () => {
    const html = render({ answer: [`First [[${B.handle}]] then [[${A.handle}]].`] });
    const list = html.slice(html.indexOf("Supporting evidence"));
    expect(list.indexOf("REVIEWS title")).toBeLessThan(list.indexOf("SURVEY title"));
  });

  it("tags interpretation units as inference", () => {
    const html = render({ answer: [`Fact [[${A.handle}]].`], interpretation: ["A reading of it [inference]."] });
    expect(html).toContain("Interpretation");
    expect(html).toContain("Inference");
    expect(html).not.toContain("[inference]");
  });
});
