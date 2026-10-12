import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import analysesFixture from "@/lib/api/__fixtures__/insights-analyses.json";
import briefFixture from "@/lib/api/__fixtures__/insights-brief.json";
import type { AnalysesResponse, EvidenceRef, InsightsBrief, Opportunity } from "@/lib/api/contracts";
import { businessLocator } from "@/lib/format";
import { indexAnalyses } from "@/lib/insights-view";
import { OpportunityCard } from "./opportunity-card";
import { OpportunityDetailView } from "./opportunity-detail";

/** Static markup escapes apostrophes and ampersands. */
const esc = (text: string) => text.replace(/&/g, "&amp;").replace(/'/g, "&#x27;");
/** UI chrome only: drop quoted passages and analyst copy so source wording cannot trip the check. */
const chrome = (html: string, o: Opportunity) =>
  [...o.supporting, ...o.contradicting]
    .flatMap((r) => [r.quote, r.note])
    .concat([o.thesis, o.status_rationale, o.next_step, ...o.gaps, ...o.caveats])
    .reduce<string>((acc, text) => (text ? acc.split(esc(text)).join("") : acc), html);

const brief = briefFixture as unknown as InsightsBrief;
const index = indexAnalyses((analysesFixture as unknown as AnalysesResponse).analyses);
const byId = (id: string): Opportunity => brief.opportunities.find((o) => o.id === id)!;

const detail = (opportunity: Opportunity) =>
  renderToStaticMarkup(
    <OpportunityDetailView ws="NORTHSTAR" brief={brief} opportunity={opportunity} analyses={index} />,
  );

describe("OpportunityDetailView", () => {
  it("renders supporting and contradicting columns with every cited passage", () => {
    const o = byId("O2");
    const html = detail(o);
    expect(html).toContain(`Supporting evidence <span class="font-normal tabular-nums text-muted">(${o.supporting.length})`);
    expect(html).toContain(`Contradicting evidence <span class="font-normal tabular-nums text-muted">(${o.contradicting.length})`);
    for (const ref of [...o.supporting, ...o.contradicting]) {
      expect(html).toContain(esc(businessLocator(ref.locator_label)));
    }
  });

  it("shows the qualitative status label and rationale, never a score or rank", () => {
    for (const o of brief.opportunities) {
      const html = detail(o);
      expect(html).toMatch(/Supported|Mixed evidence|Emerging|Needs research/i);
      expect(html).toContain(esc(o.status_rationale));
      expect(chrome(html, o)).not.toMatch(/\bscore\b|\brank(ed|ing)?\b|\/ ?10\b/i);
    }
  });

  it("renders gaps, the next step and caveats", () => {
    const o = byId("O1");
    const html = detail(o);
    expect(html).toContain("Evidence gaps");
    expect(html).toContain("Next research step");
    if (o.caveats.length > 0) expect(html).toContain("Caveats");
  });

  it("hides every figure on an item that could not be re-verified", () => {
    const o = byId("O1");
    const unverified: Opportunity = { ...o, integrity: "unverified" };
    const html = detail(unverified);
    expect(html).toContain("Could not be re-verified");
    for (const m of o.metrics) {
      if (m.display) expect(html).not.toContain(`>${m.display}<`);
    }
  });

  it("replaces a withdrawn passage with a no-longer-available card", () => {
    const o = byId("O1");
    const withdrawn: EvidenceRef = { ...o.supporting[0], integrity: "withdrawn", quote: null };
    const html = detail({ ...o, supporting: [withdrawn, ...o.supporting.slice(1)] });
    expect(html).toContain("Source no longer available");
  });
});

describe("OpportunityCard", () => {
  it("shows status, thesis and the evidence balance as text", () => {
    const o = byId("O3");
    const html = renderToStaticMarkup(<OpportunityCard ws="NORTHSTAR" opportunity={o} analyses={index} />);
    expect(html).toContain("supporting");
    expect(html).toContain("contradicting");
    expect(html).toContain("/w/NORTHSTAR/opportunities/O3");
    expect(html).not.toMatch(/\bscore\b|\brank(ed|ing)?\b/i);
  });
});
