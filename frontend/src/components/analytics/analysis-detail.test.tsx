import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import analysesFixture from "@/lib/api/__fixtures__/insights-analyses.json";
import type { Analysis, AnalysesResponse } from "@/lib/api/contracts";
import { AnalysisCard } from "./analysis-card";
import { AnalysisDetailView } from "./analysis-detail";

const analyses = (analysesFixture as unknown as AnalysesResponse).analyses;
const byId = (id: string): Analysis => analyses.find((a) => a.id === id)!;
/** Business part of the page: everything before the Technical details disclosure. */
const business = (html: string) => html.split("Technical details")[0];
const render = (a: Analysis) => renderToStaticMarkup(<AnalysisDetailView analysis={a} />);

describe("AnalysisDetailView", () => {
  it("always shows the base, unit and provenance for a computed bar analysis", () => {
    const a = byId("genz-top-pain-points");
    const html = business(render(a));
    expect(html).toContain("400 Gen Z respondents");
    expect(html).toContain("Count");
    expect(html).toContain(a.provenance.source_title);
    expect(html).toContain(`Version ${a.provenance.version}`);
    expect(html).toContain(a.provenance.table);
    expect(html).toContain("Recomputed at");
    expect(html).toContain("Computed from structured data");
    for (const row of a.rows) expect(html).toContain(row.display!);
  });

  it("renders listings as a table with humanized column headers", () => {
    const html = business(render(byId("highest-return-skus")));
    expect(html).toContain("<table");
    expect(html).toContain("Return rate (%)");
    expect(html).not.toContain("return_rate_pct");
  });

  it("shows per-row bases when the analysis has no single denominator", () => {
    const a = byId("pain-points-by-cohort");
    const html = business(render(a));
    expect(html).toContain("Shown per row");
    expect(business(render(byId("highest-return-skus")))).toContain("matching records");
    const row = a.rows[0];
    if (row.numerator != null && row.denominator != null) expect(html).toContain(`${row.numerator} of ${row.denominator}`);
  });

  it("withholds numbers and shows the callout on a mismatch", () => {
    const base = byId("genz-top-pain-points");
    const mismatch: Analysis = { ...base, status: "mismatch", value: null, display: null, rows: [] };
    const html = business(render(mismatch));
    expect(html).toContain("Result changed since curation; numbers withheld");
    expect(html).not.toContain("Computed from structured data");
    expect(html).toContain("400 Gen Z respondents");
    expect(html).toContain(base.provenance.source_title);
  });

  it("explains an unavailable dataset without numbers", () => {
    const base = byId("q3-returns-by-reason");
    const html = business(render({ ...base, status: "unavailable", value: null, display: null, rows: [] }));
    expect(html).toContain("This dataset is not currently available");
    expect(html).not.toContain("Computed from structured data");
  });

  it("keeps operation names out of the business view", () => {
    for (const a of analyses) {
      const html = business(render(a));
      expect(html).not.toMatch(/group_compare|filter_rows|aggregate\(/);
    }
  });
});

describe("AnalysisCard", () => {
  it("leads with the headline figure and its base when computed", () => {
    const a = byId("genz-top-pain-points");
    const html = renderToStaticMarkup(<AnalysisCard ws="NORTHSTAR" analysis={a} />);
    expect(html).toContain(a.rows[0].display!);
    expect(html).toContain("400 Gen Z respondents");
    expect(html).toContain("/w/NORTHSTAR/analytics/genz-top-pain-points");
  });

  it("shows no figure when numbers are withheld", () => {
    const a = byId("genz-top-pain-points");
    const html = renderToStaticMarkup(<AnalysisCard ws="NORTHSTAR" analysis={{ ...a, status: "mismatch", rows: [], value: null, display: null }} />);
    expect(html).toContain("Numbers withheld");
    expect(html).not.toContain(a.rows[0].display!);
  });
});
