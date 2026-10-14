import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import analysesFixture from "@/lib/api/__fixtures__/insights-analyses.json";
import briefFixture from "@/lib/api/__fixtures__/insights-brief.json";
import type { AnalysesResponse, EvidenceRef, InsightsBrief, Opportunity } from "@/lib/api/contracts";
import { businessLocator } from "@/lib/format";
import { indexAnalyses } from "@/lib/insights-view";
import { OpportunitiesListView, LIST_NOTE } from "./opportunities-list";
import { OpportunityCard } from "./opportunity-card";
import { OpportunityDetailView } from "./opportunity-detail";

/** Static markup escapes apostrophes, quotes and ampersands. */
const esc = (text: string) => text.replace(/&/g, "&amp;").replace(/'/g, "&#x27;").replace(/"/g, "&quot;");
/** UI chrome only: drop quoted passages and analyst copy so source wording cannot trip the check. */
const chrome = (html: string, o: Opportunity) =>
  [...o.supporting, ...o.contradicting, ...o.risks.flatMap((r) => r.evidence)]
    .flatMap((r) => [r.quote, r.note])
    .concat([o.thesis, o.status_rationale, o.next_step, o.next_investigation, o.why_it_matters?.text ?? null, ...o.gaps, ...o.caveats])
    .concat(o.risks.map((r) => r.text))
    .reduce<string>((acc, text) => (text ? acc.split(esc(text)).join("") : acc), html);
/** Everything outside the "Technical details" disclosure. */
const business = (html: string) => html.replace(/<details[\s\S]*?<\/details>/g, "");

const brief = briefFixture as unknown as InsightsBrief;
const index = indexAnalyses((analysesFixture as unknown as AnalysesResponse).analyses);
const byId = (id: string): Opportunity => brief.opportunities.find((o) => o.id === id)!;

const detail = (opportunity: Opportunity) =>
  renderToStaticMarkup(<OpportunityDetailView ws="NORTHSTAR" brief={brief} opportunity={opportunity} analyses={index} />);
const card = (opportunity: Opportunity) =>
  renderToStaticMarkup(<OpportunityCard ws="NORTHSTAR" opportunity={opportunity} analyses={index} />);

describe("OpportunityCard", () => {
  it("shows title, status pill, thesis with its claim type, lead figure, balance, gaps and source mix", () => {
    const o = byId("O1");
    const html = card(o);
    expect(html).toContain(esc(o.title));
    expect(html).toContain('data-status="supported"');
    expect(html).toContain(esc(o.thesis));
    expect(html).toContain('data-claim="inference"');
    expect(html).toContain("27.0%");
    expect(html).toContain('data-claim="derived"');
    expect(html).toMatch(/>5<\/span> supporting/);
    expect(html).toMatch(/>2<\/span> contradicting/);
    expect(html).toContain("2 open gaps");
    expect(html).toContain('aria-label="Evidence by source type"');
    expect(html).toContain("/w/NORTHSTAR/opportunities/O1");
  });

  it("labels needs_research as Needs validation and never shows a score", () => {
    const o = byId("O4");
    const html = card(o);
    expect(html).toContain("Needs validation");
    expect(chrome(html, o)).not.toMatch(/\bscore\b|\brank(ed|ing)?\b|\/ ?10\b/i);
  });

  it("withholds the lead figure when the item could not be re-verified", () => {
    const o = byId("O1");
    const html = card({ ...o, integrity: "unverified" });
    expect(html).not.toContain("27.0%");
    expect(html).toContain("Could not be re-verified");
  });
});

describe("OpportunitiesListView", () => {
  it("orders opportunities by status strength and keeps the honest note", () => {
    const shuffled: InsightsBrief = { ...brief, opportunities: [byId("O4"), byId("O3"), byId("O2"), byId("O1")] };
    const html = renderToStaticMarkup(<OpportunitiesListView ws="NORTHSTAR" brief={shuffled} analyses={index} />);
    expect(LIST_NOTE).toContain("there are no scores");
    const positions = ["O1", "O2", "O3", "O4"].map((id) => html.indexOf(`/opportunities/${id}"`));
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });
});

describe("OpportunityDetailView", () => {
  it("renders supporting and contradicting evidence with every cited passage", () => {
    const o = byId("O2");
    const html = detail(o);
    expect(html).toContain(`Supporting evidence <span class="font-normal tabular-nums text-muted">(${o.supporting.length})`);
    expect(html).toContain(`Contradicting evidence <span class="font-normal tabular-nums text-muted">(${o.contradicting.length})`);
    for (const ref of [...o.supporting, ...o.contradicting]) {
      expect(html).toContain(esc(businessLocator(ref.locator_label)));
    }
    expect(html).toContain(`Supporting: ${o.supporting.length} sources; Contradicting: ${o.contradicting.length} sources`);
  });

  it("renders thesis, why it matters and each risk with its claim tag", () => {
    const o = byId("O1");
    const html = detail(o);
    expect(html).toContain("Strategic thesis");
    expect(html).toContain(esc(o.why_it_matters!.text));
    expect(html).toContain("Risks and blockers");
    for (const risk of o.risks) {
      const at = html.indexOf(esc(risk.text));
      expect(at).toBeGreaterThan(-1);
      expect(html.slice(at, at + esc(risk.text).length + 120)).toContain(`data-claim="${risk.claim_type}"`);
      for (const e of risk.evidence) expect(html).toContain(esc(e.source.title));
    }
  });

  it("charts comparable figures together with their bases", () => {
    const html = detail(byId("O2"));
    expect(html).toContain("Lack of personalization is the top frustration");
    expect(html).toContain("Value Seekers");
    expect(html).toContain("10.6%");
  });

  it("links the next investigation into Chat and the deck with related items", () => {
    const o = byId("O4");
    const html = detail(o);
    expect(html).toContain(`href="/w/NORTHSTAR/ask?q=${esc(encodeURIComponent(o.next_investigation!))}"`);
    expect(html).toContain("Investigate in Chat");
    expect(html).toContain('href="/w/NORTHSTAR/insights/deck?s=sustainability-proof&amp;o=O4&amp;a=genz-top-pain-points"');
    expect(html).toContain('href="/w/NORTHSTAR/insights#sustainability-proof"');
    expect(html).toContain('href="/w/NORTHSTAR/analytics/genz-top-pain-points"');
  });

  it("shows the qualitative status and rationale, never a score; handles only in technical details", () => {
    for (const o of brief.opportunities) {
      const html = detail(o);
      expect(html).toMatch(/Supported|Mixed evidence|Emerging|Needs validation/);
      expect(html).toContain(esc(o.status_rationale));
      expect(chrome(html, o)).not.toMatch(/\bscore\b|\brank(ed|ing)?\b|\/ ?10\b/i);
      expect(business(html)).not.toContain(o.supporting[0].handle);
      expect(html).toContain("Technical details");
    }
  });

  it("withholds every figure on an item that could not be re-verified", () => {
    const o = byId("O2");
    const html = detail({ ...o, integrity: "unverified" });
    expect(html).toContain("Could not be re-verified");
    for (const m of o.metrics) {
      if (m.display) expect(html).not.toContain(m.display);
    }
  });

  it("says so when some evidence changed", () => {
    const html = detail({ ...byId("O3"), integrity: "partial" });
    expect(html).toContain("Some evidence changed");
  });

  it("replaces a withdrawn passage with a no-longer-available card", () => {
    const o = byId("O1");
    const withdrawn: EvidenceRef = { ...o.supporting[0], integrity: "withdrawn", quote: null };
    const html = detail({ ...o, supporting: [withdrawn, ...o.supporting.slice(1)] });
    expect(html).toContain("Source no longer available");
  });
});
