import { describe, expect, it } from "vitest";
import { buildSearchQuery, groupSearchResults } from "./search";

describe("buildSearchQuery", () => {
  it("defaults k to 10 and omits empty filters", () => {
    const qs = new URLSearchParams(buildSearchQuery({ q: "gen z", mode: "full" }));
    expect(qs.get("q")).toBe("gen z");
    expect(qs.get("mode")).toBe("full");
    expect(qs.get("k")).toBe("10");
    expect(qs.has("source_class")).toBe(false);
  });
  it("repeats source_class and source params", () => {
    const raw = buildSearchQuery({
      q: "a&b",
      mode: "hybrid",
      k: 5,
      sourceClasses: ["internal", "market"],
      sources: ["S1", "S2"],
      maxConfidentiality: "confidential",
    });
    const qs = new URLSearchParams(raw);
    expect(qs.getAll("source_class")).toEqual(["internal", "market"]);
    expect(qs.getAll("source")).toEqual(["S1", "S2"]);
    expect(qs.get("q")).toBe("a&b");
    expect(qs.get("k")).toBe("5");
    expect(qs.get("max_confidentiality")).toBe("confidential");
    expect(raw.match(/source_class=/g)).toHaveLength(2);
  });
});

describe("groupSearchResults", () => {
  const item = (rank: number, code: string) =>
    ({
      rank,
      handle: `h${rank}`,
      locator_label: `p. ${rank}`,
      source_code: code,
      source_title: `Title ${code}`,
      source_type: "pdf",
      source_class: "market",
      anchor: { child_id: `c${rank}`, lane: "dense", char_start: 0, char_end: 1 },
      snippet: { text: "x", mark_start: 0, mark_end: 1, truncated_left: false, truncated_right: false },
      scores: { rrf: 0.1, rerank: null, fused_rank: rank, lanes: {} },
    }) as const;

  it("groups by source in first-appearance order, keeping rank order inside each group", () => {
    const groups = groupSearchResults([item(3, "A"), item(1, "B"), item(2, "A")]);
    expect(groups.map((g) => g.sourceCode)).toEqual(["B", "A"]);
    expect(groups[1].items.map((i) => i.rank)).toEqual([2, 3]);
    expect(groups[0]).toMatchObject({ title: "Title B", sourceClass: "market", sourceType: "pdf" });
  });

  it("returns no groups for no results", () => {
    expect(groupSearchResults([])).toEqual([]);
  });
});
