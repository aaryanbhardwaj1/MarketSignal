import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import analysesFixture from "@/lib/api/__fixtures__/insights-analyses.json";
import briefFixture from "@/lib/api/__fixtures__/insights-brief.json";
import type { AnalysesResponse, InsightsBrief, Signal } from "@/lib/api/contracts";
import { indexAnalyses } from "@/lib/insights-view";
import { INSIGHT_CATEGORIES } from "@/lib/views/insights";
import { InsightCard } from "./insight-card";
import { NoInsights } from "./insights-page";
import { InsightsView } from "./insights-view";

const brief = briefFixture as unknown as InsightsBrief;
const analyses = indexAnalyses((analysesFixture as unknown as AnalysesResponse).analyses);
const signal = (id: string): Signal => brief.signals.find((s) => s.id === id)!;
const esc = (text: string) => text.replace(/&/g, "&amp;").replace(/'/g, "&#x27;").replace(/"/g, "&quot;");

const card = (s: Signal, selected = false) =>
  renderToStaticMarkup(
    <InsightCard ws="NORTHSTAR" signal={s} brief={brief} analyses={analyses} selected={selected} onToggle={() => {}} />,
  );

describe("InsightCard", () => {
  it("tags the statement and the implication with their claim types", () => {
    const s = signal("fit-friction");
    const html = card(s);
    expect(html).toContain(esc(s.title));
    expect(html).toContain('data-claim="observed"');
    expect(html).toContain("So what");
    expect(html).toContain('data-claim="inference"');
    expect(html).toContain('data-status="strong_evidence"');
  });

  it("shows the strongest recomputed figure with its base, tagged Derived", () => {
    const html = card(signal("fit-friction"));
    expect(html).toContain("27.0%");
    expect(html).toContain('data-claim="derived"');
    expect(html).toMatch(/Gen Z respondents/);
  });

  it("shows supporting and contradicting counts", () => {
    const s = signal("premium-ceiling");
    const html = card(s);
    expect(html).toContain(`${s.support_count} supporting`);
    expect(html).toContain(`${s.contradiction_count} contradicting`);
  });

  it("labels a cited forecast with its source and never as observed", () => {
    const s = signal("category-growth-outlook");
    const html = card(s);
    expect(html).toContain('data-claim="forecast"');
    const source = s.evidence.find((e) => e.states_projection)!.source.title;
    expect(html).toContain(`Forecast stated by ${esc(source)}`);
    expect(html).toContain("Open questions");
  });

  it("labels an unsourced outlook as a hypothesis", () => {
    const html = card(signal("creator-discovery-outlook"));
    expect(html).toContain('data-claim="hypothesis"');
    expect(html).toContain("Hypothesis: no cited source states this projection");
    expect(html).not.toContain("Forecast stated by");
  });

  it("withholds every number when the item could not be re-verified", () => {
    const html = card({ ...signal("fit-friction"), integrity: "unverified" });
    expect(html).not.toContain("27.0%");
    expect(html).not.toContain("19.0%");
    expect(html).toContain("Figures withheld");
    expect(html).toContain("Could not be re-verified");
  });

  it("discloses every cited passage, caveats and related items", () => {
    const s = signal("fit-friction");
    const html = card(s);
    for (const e of s.evidence) expect(html).toContain(esc(e.quote!));
    expect(html).toContain(esc(s.caveats[0]!));
    expect(html).toContain('href="/w/NORTHSTAR/opportunities/O1"');
    expect(html).toContain('href="/w/NORTHSTAR/insights#fit-returns"');
  });

  it("anchors the card on its id and reflects selection", () => {
    const html = card(signal("fit-friction"), true);
    expect(html).toContain('id="fit-friction"');
    expect(html).toMatch(/type="checkbox"[^>]*checked=""/);
  });

  it("never shows a numeric score", () => {
    expect(card(signal("premium-ceiling"))).not.toMatch(/\bscore\b|\bconfidence\b/i);
  });
});

describe("InsightsView", () => {
  const view = () =>
    renderToStaticMarkup(
      <InsightsView
        ws="NORTHSTAR"
        brief={brief}
        analyses={analyses}
        client="Northstar Athletics"
        now={new Date(brief.computed_at)}
      />,
    );

  it("renders all six categories with their counts", () => {
    const html = view();
    for (const c of INSIGHT_CATEGORIES) expect(html).toContain(`id="insights-${c.id}"`);
    expect(html).toContain("Risks / Blockers");
    for (const s of brief.signals) expect(html).toContain(`id="${s.id}"`);
  });

  it("explains the page and its provenance", () => {
    const html = view();
    expect(html).toContain("Evidence-backed patterns and what they mean for Northstar Athletics&#x27; growth.");
    expect(html).toContain("Curated analyst brief · re-verified against current evidence");
  });

  it("summarises the findings with real counts", () => {
    const html = view();
    expect(html).toContain(`>${brief.signals.length}<`);
    expect(html).toContain("Findings by evidence status");
  });

  it("links strategic opportunities into Growth Opportunities without duplicating their detail", () => {
    const html = view();
    for (const o of brief.opportunities) expect(html).toContain(`href="/w/NORTHSTAR/opportunities/${o.id}"`);
    expect(html).not.toContain(esc(brief.opportunities[0]!.next_step));
  });

  it("starts a presentation from every strategic opportunity when nothing is selected", () => {
    expect(view()).toContain('href="/w/NORTHSTAR/insights/deck?o=O1,O2,O3,O4"');
  });

  it("shows a drift notice when sources changed", () => {
    const html = renderToStaticMarkup(
      <InsightsView
        ws="NORTHSTAR"
        brief={{ ...brief, corpus_check: { status: "drift", drifted_sources: ["X"] } }}
        analyses={analyses}
      />,
    );
    expect(html).toContain("could not be re-verified against current evidence");
    expect(html).toContain("this client&#x27;s growth");
  });
});

describe("NoInsights", () => {
  it("teaches what the page is for", () => {
    expect(renderToStaticMarkup(<NoInsights ws="NORTHSTAR" />)).toContain(
      "Review evidence-backed patterns and strategic implications.",
    );
  });
});
