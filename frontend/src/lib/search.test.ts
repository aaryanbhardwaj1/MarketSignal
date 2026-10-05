import { describe, expect, it } from "vitest";
import {
  buildSearchQuery,
  flagMessage,
  formatStageLine,
  formatTimings,
  parseSearchMode,
  parseSourceClasses,
  searchHref,
} from "./search";

describe("parseSearchMode", () => {
  it("accepts the four modes", () => {
    for (const m of ["full", "hybrid", "dense", "lexical"]) expect(parseSearchMode(m)).toBe(m);
  });
  it("falls back to full for unknown or missing values", () => {
    expect(parseSearchMode("bogus")).toBe("full");
    expect(parseSearchMode("")).toBe("full");
    expect(parseSearchMode(null)).toBe("full");
    expect(parseSearchMode(undefined)).toBe("full");
    expect(parseSearchMode("FULL")).toBe("full");
  });
});

describe("parseSourceClasses", () => {
  it("filters unknowns, dedupes and orders canonically", () => {
    expect(parseSourceClasses(["market", "nope", "internal", "market"])).toEqual(["internal", "market"]);
    expect(parseSourceClasses("customer")).toEqual(["customer"]);
    expect(parseSourceClasses(undefined)).toEqual([]);
  });
});

describe("flagMessage", () => {
  it("maps known flags and passes unknown ones through", () => {
    expect(flagMessage("RERANKER_UNAVAILABLE")).toBe("Reranker unavailable: showing fused order");
    expect(flagMessage("RETRIEVAL_LEXICAL_FALLBACK")).toBe(
      "Embedding model unavailable: keyword results only",
    );
    expect(flagMessage("SOMETHING_NEW")).toBe("SOMETHING_NEW");
  });
});

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

describe("searchHref", () => {
  it("keeps q, mode and repeated source_class in the URL", () => {
    const href = searchHref("NORTHSTAR", "x y", "dense", ["customer", "financial"]);
    expect(href).toBe("/w/NORTHSTAR/search?q=x+y&mode=dense&source_class=customer&source_class=financial");
  });
});

describe("formatStageLine", () => {
  it("shows both lanes, fused rank and rerank to 2 decimals", () => {
    expect(
      formatStageLine({ rrf: 0.03, rerank: 0.8749, fused_rank: 2, lanes: { dense: 3, lexical: 1 } }),
    ).toBe("dense #3 · keyword #1 · fused #2 · rerank 0.87");
  });
  it("omits missing lanes and null rerank", () => {
    expect(formatStageLine({ rrf: 0.01, rerank: null, fused_rank: 1, lanes: { lexical: 4 } })).toBe(
      "keyword #4 · fused #1",
    );
    expect(formatStageLine({ rrf: 0.01, rerank: 0, fused_rank: 1, lanes: { dense: 1 } })).toBe(
      "dense #1 · fused #1 · rerank 0.00",
    );
  });
});

describe("formatTimings", () => {
  it("puts total first and strips _ms suffixes", () => {
    expect(formatTimings({ embed_ms: 12.34, dense_ms: 5, total_ms: 30 })).toBe(
      "total 30 ms · embed 12.3 ms · dense 5 ms",
    );
    expect(formatTimings({})).toBe("");
  });
});
