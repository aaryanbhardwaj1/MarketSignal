import { describe, expect, it } from "vitest";
import analysesFixture from "@/lib/api/__fixtures__/insights-analyses.json";
import type { AnalysesResponse, Analysis } from "@/lib/api/contracts";
import {
  analysisDeckHref,
  chooseChart,
  compactUsd,
  filterChipLabel,
  filterChips,
  followUpHref,
  formatUnitValue,
  groupByArea,
  groupedSeries,
  interpretationView,
  isTemporalKey,
  lineSeries,
  listingBars,
  populationLine,
  summaryView,
  topBars,
  valueFormatter,
} from "./analytics";

const analyses = (analysesFixture as unknown as AnalysesResponse).analyses;
const byId = (id: string): Analysis => {
  const found = analyses.find((a) => a.id === id);
  if (!found) throw new Error(`fixture has no ${id}`);
  return found;
};
const withheld = (a: Analysis): Analysis => ({ ...a, status: "mismatch", rows: [], value: null, display: null, summary: null, summary_status: "unverified" });

describe("groupByArea", () => {
  it("groups by business area in a fixed reading order and only lists areas that exist", () => {
    const groups = groupByArea(analyses);
    expect(groups.map((g) => g.area)).toEqual([
      "Customer friction",
      "Customer satisfaction",
      "Willingness to pay",
      "Product performance",
      "Channels and growth",
    ]);
    expect(groups[0].analyses.map((a) => a.id)).toEqual(["genz-top-pain-points", "pain-points-by-cohort", "fit-and-personalization-by-segment"]);
    expect(groups.flatMap((g) => g.analyses)).toHaveLength(analyses.length);
  });

  it("drops empty areas and puts analyses without an area last", () => {
    const one = { ...byId("nps-by-cohort"), business_area: null };
    const groups = groupByArea([one, byId("q3-returns-by-reason")]);
    expect(groups.map((g) => g.area)).toEqual(["Product performance", "Other analyses"]);
  });
});

describe("chooseChart", () => {
  it("picks the chart from presentation, operation, grouping and time", () => {
    expect(chooseChart(byId("genz-top-pain-points"))).toBe("hbar");
    expect(chooseChart(byId("price-sensitivity-by-cohort"))).toBe("hbar");
    expect(chooseChart(byId("pain-points-by-cohort"))).toBe("grouped");
    expect(chooseChart(byId("fit-and-personalization-by-segment"))).toBe("grouped");
    expect(chooseChart(byId("highest-return-skus"))).toBe("table");
    expect(chooseChart(byId("social-shop-sales-by-quarter"))).toBe("line");
  });

  it("withholds numbers when the result is not computed and handles empty or single results", () => {
    expect(chooseChart(withheld(byId("genz-top-pain-points")))).toBe("withheld");
    expect(chooseChart({ ...byId("genz-top-pain-points"), status: "unavailable" })).toBe("withheld");
    expect(chooseChart({ ...byId("genz-top-pain-points"), rows: [] })).toBe("empty");
    expect(chooseChart({ ...byId("genz-top-pain-points"), presentation: "single", value: 3, display: "3", rows: [] })).toBe("single");
  });

  it("falls back to a table when a two-way grouping has too many series to colour", () => {
    const base = byId("pain-points-by-cohort");
    const rows = Array.from({ length: 25 }, (_, i) => ({
      group: { cohort: `C${i % 5}`, measure: `M${Math.floor(i / 5)}` },
      value: i,
      display: String(i),
    }));
    expect(chooseChart({ ...base, rows })).toBe("table");
  });
});

describe("temporal detection", () => {
  it("recognises period-like grouping keys", () => {
    expect(isTemporalKey("period")).toBe(true);
    expect(isTemporalKey("fiscal_quarter")).toBe(true);
    expect(isTemporalKey("month")).toBe(true);
    expect(isTemporalKey("segment")).toBe(false);
    expect(isTemporalKey("reason")).toBe(false);
  });

  it("builds the line series in row order", () => {
    const line = lineSeries(byId("social-shop-sales-by-quarter"));
    expect(line?.x).toEqual(["Jan-Mar 2026", "Apr-Jun 2026"]);
    expect(line?.values).toEqual([886762, 2146098]);
  });
});

describe("topBars", () => {
  it("returns the largest groups first, emphasising only the leader", () => {
    const bars = topBars(byId("genz-top-pain-points"), 3);
    expect(bars).toHaveLength(3);
    expect(bars[0]).toMatchObject({ label: "Fit inconsistency", value: 108, emphasis: true });
    expect(bars.slice(1).every((b) => !b.emphasis)).toBe(true);
    expect(bars[0].value).toBeGreaterThanOrEqual(bars[1].value);
  });

  it("is empty when numbers are withheld", () => {
    expect(topBars(withheld(byId("genz-top-pain-points")))).toEqual([]);
  });
});

describe("listingBars", () => {
  it("charts the first numeric column of a listing, labelled by the row's name", () => {
    const { measure, bars } = listingBars(byId("highest-return-skus"), 3);
    expect(measure?.column).toBe("return_rate_pct");
    expect(measure?.label).toBe("Return rate (%)");
    expect(bars).toHaveLength(3);
    expect(bars[0].label).not.toMatch(/^NS-/);
    expect(bars[0].emphasis).toBe(true);
  });
});

describe("groupedSeries", () => {
  it("uses the dimension with fewer values as the series", () => {
    const seg = groupedSeries(byId("fit-and-personalization-by-segment"));
    expect(seg?.series.map((s) => s.name)).toEqual(["Fit inconsistency", "Lack of personalization"]);
    expect(seg?.categories).toHaveLength(5);
    const cohort = groupedSeries(byId("pain-points-by-cohort"));
    expect(cohort?.series.map((s) => s.name)).toEqual(["Gen Z (18-27)", "Aged 28+"]);
    expect(cohort?.series[0].values[0]).toBe(27);
  });
});

describe("formatting", () => {
  it("formats by unit and prefers the endpoint's display for row values", () => {
    expect(formatUnitValue(27, "percent")).toBe("27.0%");
    expect(formatUnitValue(1200, "usd")).toBe("$1,200");
    expect(formatUnitValue(3.9, "score")).toBe("3.90");
    expect(formatUnitValue(108, "count")).toBe("108");
    const fmt = valueFormatter(byId("social-shop-sales-by-quarter"));
    expect(fmt(886762)).toBe("$886,762");
    expect(fmt(2_000_000)).toBe("$2.0M");
    expect(compactUsd(500_000)).toBe("$500K");
    expect(compactUsd(120)).toBe("$120");
  });
});

describe("filter chips", () => {
  it("names the Gen Z age bands as one readable chip", () => {
    expect(filterChips(byId("genz-top-pain-points"))).toEqual(["Age group: Gen Z (18-27)"]);
  });

  it("collapses other contiguous age bands into a range and leaves other filters readable", () => {
    expect(filterChipLabel({ column: "age_group", label: "Age group", op: "in", values: ["28-34", "35-44"] })).toBe("Age group: 28-44");
    expect(filterChipLabel({ column: "quarter", label: "Quarter", op: "eq", values: ["2026-Q3"] })).toBe("Quarter: Q3 2026");
    expect(filterChipLabel({ column: "rating", label: "", op: "gte", values: [4] })).toBe("Rating: at least 4");
  });
});

describe("populationLine", () => {
  it("states the population in plain words", () => {
    expect(populationLine(byId("genz-top-pain-points"))).toBe("400 Gen Z respondents");
    expect(populationLine(byId("pain-points-by-cohort"))).toBe("600 respondents");
    expect(populationLine({ ...byId("q3-returns-by-reason") })).toBe("30 return records");
  });
});

describe("summary and interpretation", () => {
  it("shows a verified summary and withholds an unverified one", () => {
    expect(summaryView(byId("genz-top-pain-points")).kind).toBe("shown");
    expect(summaryView(withheld(byId("genz-top-pain-points"))).kind).toBe("withheld");
    expect(summaryView({ ...byId("genz-top-pain-points"), summary: null, summary_status: "absent" }).kind).toBe("absent");
  });

  it("withholds the interpretation when numbers are withheld or it is not verified", () => {
    expect(interpretationView(byId("genz-top-pain-points")).kind).toBe("shown");
    expect(interpretationView(withheld(byId("genz-top-pain-points"))).kind).toBe("withheld");
    const unverified = { ...byId("genz-top-pain-points"), interpretation_status: "unverified" } as Analysis;
    expect(interpretationView(unverified).kind).toBe("withheld");
    expect(interpretationView(byId("price-sensitivity-by-segment")).kind).toBe("absent");
  });
});

describe("links", () => {
  it("builds the deck selection URL with encoded, comma-separated ids", () => {
    expect(analysisDeckHref("NORTHSTAR", { analyses: ["q3-returns-by-reason"], signals: ["fit-returns", "a b"] })).toBe(
      "/w/NORTHSTAR/insights/deck?s=fit-returns,a%20b&a=q3-returns-by-reason",
    );
    expect(analysisDeckHref("NORTHSTAR", { analyses: ["x"] })).toBe("/w/NORTHSTAR/insights/deck?a=x");
  });

  it("pre-fills a follow-up question in Ask", () => {
    expect(followUpHref("NORTHSTAR", "Why & how?")).toBe("/w/NORTHSTAR/ask?q=Why+%26+how%3F");
  });
});
