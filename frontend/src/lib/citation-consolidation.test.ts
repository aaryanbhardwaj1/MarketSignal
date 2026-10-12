import { describe, expect, it } from "vitest";
import type { AnyCitationCard, CitationCard, ResultCitationCard } from "./api/types";
import { dedupeChips, groupPlaceholders, numberCitations, prepareMarkdown, splitPlaceholders } from "./citations";

const card = (handle: string): CitationCard => ({
  kind: "evidence",
  handle,
  source_code: "S",
  source_title: `Title ${handle}`,
  source_class: "customer",
  source_type: "survey",
  locator_label: "Row 1",
  anchor_child_id: null,
  char_start: 0,
  char_end: 10,
  parent_content_hash: null,
});
const A = "NS/A@v1:R1";
const B = "NS/B@v1:R2";
const C = "NS/C@v1:R3";
const RID = "3f2b7c9e-8a41-4d6b-b0a1-5c2d9e7f1a30";
const result: ResultCitationCard = { kind: "result", result_id: RID, source_code: "S", dataset: "S:1", op: "aggregate", summary: "count" };
const cards: AnyCitationCard[] = [card(C), card(A), card(B), result];

describe("numberCitations", () => {
  it("numbers evidence by first appearance across texts and de-duplicates by handle", () => {
    const n = numberCitations([`x [[${B}]] y [[${A}]]`, `z [[${B}]] [[result:${RID}]]`], cards);
    expect(n.evidence.map((c) => c.handle)).toEqual([B, A, C]);
    expect(n.evidenceNumber.get(B)).toBe(1);
    expect(n.evidenceNumber.get(A)).toBe(2);
    expect(n.evidenceNumber.get(C)).toBe(3);
    expect(n.results.map((r) => r.result_id)).toEqual([RID]);
    expect(n.resultNumber.get(RID)).toBe(1);
  });

  it("ignores handles without a card", () => {
    const n = numberCitations([`[[NS/X@v1:R9]] [[${A}]]`], [card(A)]);
    expect([...n.evidenceNumber.entries()]).toEqual([[A, 1]]);
  });
});

describe("chip grouping", () => {
  it("merges adjacent chips separated by whitespace and de-duplicates repeats", () => {
    const prepared = prepareMarkdown(`Claim [[${A}]] [[${B}]][[${A}]]. Next [[${B}]]`, { cards });
    const groups = groupPlaceholders(splitPlaceholders(prepared.source));
    const chipGroups = groups.filter((g) => g.kind === "chips");
    expect(chipGroups).toHaveLength(2);
    const first = chipGroups[0];
    if (first.kind !== "chips") throw new Error("expected chips");
    expect(first.indices).toHaveLength(3);
    const unique = dedupeChips(first.indices.map((i) => prepared.tokens[i]));
    expect(unique.map((t) => (t.kind === "handle" ? t.handle : t.kind))).toEqual([A, B]);
    expect(groups.map((g) => (g.kind === "text" ? g.text : "#"))).toEqual(["Claim ", "#", ". Next ", "#"]);
  });
});
