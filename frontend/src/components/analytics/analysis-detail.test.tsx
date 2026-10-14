import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import analysesFixture from "@/lib/api/__fixtures__/insights-analyses.json";
import type { Analysis, AnalysesResponse } from "@/lib/api/contracts";
import { AnalysisCard } from "./analysis-card";
import { AnalysisDetailView } from "./analysis-detail";
import { AnalysisActions } from "./analysis-page";
import { AnalysisAreas } from "./analytics-view";

const analyses = (analysesFixture as unknown as AnalysesResponse).analyses;
const byId = (id: string): Analysis => analyses.find((a) => a.id === id)!;
/** Business part of the page: everything before the Technical details disclosure. */
const business = (html: string) => html.split("Technical details")[0];
const render = (a: Analysis) => renderToStaticMarkup(<AnalysisDetailView ws="NORTHSTAR" analysis={a} />);
const mismatch = (a: Analysis): Analysis => ({ ...a, status: "mismatch", value: null, display: null, rows: [], summary: null, summary_status: "unverified" });

describe("AnalysisDetailView", () => {
  it("states what was measured with readable filter chips, population and provenance", () => {
    const a = byId("genz-top-pain-points");
    const html = business(render(a));
    expect(html).toContain(a.question);
    expect(html).toContain("Age group: Gen Z (18-27)");
    expect(html).toContain("400 Gen Z respondents");
    expect(html).toContain(a.provenance.source_title);
    expect(html).toContain(`Version ${a.provenance.version}`);
    expect(html).toContain("Recomputed at");
    expect(html).toContain("/w/NORTHSTAR/evidence?q=");
  });

  it("charts a categorical result with every group's value", () => {
    const a = byId("genz-top-pain-points");
    const html = business(render(a));
    expect(html).toContain("<figure");
    for (const row of a.rows) expect(html).toContain(row.display!);
  });

  it("labels the interpretation as an inference", () => {
    const a = byId("genz-top-pain-points");
    const html = business(render(a));
    expect(html).toContain("Interpretation");
    expect(html).toContain(a.interpretation!.text);
    expect(html).toContain('data-claim="inference"');
  });

  it("withholds numbers and the interpretation on a mismatch", () => {
    const base = byId("genz-top-pain-points");
    const html = business(render(mismatch(base)));
    expect(html).toContain("Numbers withheld");
    expect(html).toContain("Interpretation withheld");
    expect(html).not.toContain(base.interpretation!.text);
    expect(html).not.toContain("<figure");
    expect(html).not.toContain(">108<");
    expect(html).toContain("400 Gen Z respondents");
  });

  it("explains an unavailable dataset without numbers", () => {
    const base = byId("q3-returns-by-reason");
    const html = business(render({ ...base, status: "unavailable", value: null, display: null, rows: [] }));
    expect(html).toContain("This dataset is not currently available");
    expect(html).not.toContain("<figure");
  });

  it("renders listings as a table with humanized, right-aligned numeric columns", () => {
    const html = business(render(byId("highest-return-skus")));
    expect(html).toContain("<table");
    expect(html).toContain("Return rate (%)");
    expect(html).not.toContain("return_rate_pct");
    expect(html).toContain("matching records");
  });

  it("links the insights and opportunities that use the analysis", () => {
    const a = byId("q3-returns-by-reason");
    const titles = { signals: new Map([["fit-returns", "Fit drives returns"]]), opportunities: new Map([["O1", "Fit confidence"]]) };
    const html = renderToStaticMarkup(<AnalysisDetailView ws="NORTHSTAR" analysis={a} titles={titles} />);
    expect(html).toContain('href="/w/NORTHSTAR/insights#fit-returns"');
    expect(html).toContain("Fit drives returns");
    expect(html).toContain('href="/w/NORTHSTAR/opportunities/O1"');
    expect(html).toContain("Fit confidence");
  });

  it("keeps operation names out of the business view", () => {
    for (const a of analyses) {
      const html = business(render(a));
      expect(html).not.toMatch(/group_compare|filter_rows|aggregate/);
    }
  });
});

describe("AnalysisActions", () => {
  it("adds the analysis and its insights to a deck and pre-fills a follow-up", () => {
    const a = byId("q3-returns-by-reason");
    const html = renderToStaticMarkup(<AnalysisActions ws="NORTHSTAR" analysis={a} />);
    expect(html).toContain("Add to presentation");
    expect(html).toContain("/w/NORTHSTAR/insights/deck?s=knit-runner-durability,fit-returns&amp;a=q3-returns-by-reason");
    expect(html).toContain("/w/NORTHSTAR/ask?q=Why+were+products+returned");
  });
});

describe("AnalysisCard", () => {
  it("shows the verified summary as derived, a small chart and the population", () => {
    const a = byId("genz-top-pain-points");
    const html = renderToStaticMarkup(<AnalysisCard ws="NORTHSTAR" analysis={a} />);
    expect(html).toContain(a.summary!);
    expect(html).toContain('data-claim="derived"');
    expect(html).toContain("<figure");
    expect(html).toContain("400 Gen Z respondents");
    expect(html).toContain("/w/NORTHSTAR/analytics/genz-top-pain-points");
  });

  it("shows no figure when numbers are withheld", () => {
    const a = byId("genz-top-pain-points");
    const html = renderToStaticMarkup(<AnalysisCard ws="NORTHSTAR" analysis={mismatch(a)} />);
    expect(html).toContain("Numbers withheld");
    expect(html).not.toContain(a.summary!);
    expect(html).not.toContain("<figure");
  });

  it("uses a trend line for time series", () => {
    const html = renderToStaticMarkup(<AnalysisCard ws="NORTHSTAR" analysis={byId("social-shop-sales-by-quarter")} />);
    expect(html).toContain("$2,146,098");
    expect(html).toContain("<svg");
  });
});

describe("AnalysisAreas", () => {
  it("groups analyses under their business area headings", () => {
    const html = renderToStaticMarkup(<AnalysisAreas ws="NORTHSTAR" analyses={analyses} />);
    const order = ["Customer friction", "Customer satisfaction", "Willingness to pay", "Product performance", "Channels and growth"].map((t) =>
      html.indexOf(`>${t}<`),
    );
    expect(order.every((i) => i >= 0)).toBe(true);
    expect([...order].sort((x, y) => x - y)).toEqual(order);
    expect(html.indexOf("Q3 2026 returns by reason")).toBeGreaterThan(order[3]);
    expect(html.indexOf("Q3 2026 returns by reason")).toBeLessThan(order[4]);
  });
});
