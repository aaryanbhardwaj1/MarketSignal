import { describe, expect, it } from "vitest";
import { parseSections } from "./answer-sections";

describe("parseSections", () => {
  it("parses a generated answer and drops non-string / blank units", () => {
    expect(
      parseSections({
        answer: ["A [[X/Y@v1:p1]].", 3, " "],
        findings: ["F"],
        interpretation: ["I [inference]."],
        gaps: ["G"],
      }),
    ).toEqual({
      kind: "generated",
      answer: ["A [[X/Y@v1:p1]]."],
      findings: ["F"],
      conflicts: [],
      interpretation: ["I [inference]."],
      gaps: ["G"],
    });
  });

  it("recognises the evidence-only fallback", () => {
    expect(parseSections({ evidence_only: ["u1", "u2"], reason: "LLM_SYNTHESIS_UNAVAILABLE" })).toEqual({
      kind: "evidence_only",
      units: ["u1", "u2"],
      reason: "LLM_SYNTHESIS_UNAVAILABLE",
    });
  });

  it("recognises abstention", () => {
    expect(parseSections({ answer: ["No answer"], gaps: ["Missing"], abstained: true })).toEqual({
      kind: "abstained",
      answer: ["No answer"],
      gaps: ["Missing"],
    });
  });

  it("falls back to none for missing or empty payloads", () => {
    expect(parseSections(null)).toEqual({ kind: "none" });
    expect(parseSections([])).toEqual({ kind: "none" });
    expect(parseSections({ answer: [] })).toEqual({ kind: "none" });
  });
});
