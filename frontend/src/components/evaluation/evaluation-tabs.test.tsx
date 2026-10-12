import { renderToStaticMarkup } from "react-dom/server";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, className }: { href: string; children: unknown; className?: string }) => (
    <a href={href} className={className}>
      {children as never}
    </a>
  ),
}));

import catalogJson from "@/lib/api/__fixtures__/evaluation-catalog.json";
import type { EvalCatalog, MetricUnit } from "@/lib/api/contracts";
import { formatEvalValue, formatSigned } from "@/lib/eval-view";
import { formatBytes, formatDateTime, formatNumber } from "@/lib/format";
import { AnalyticsTab } from "./analytics-tab";
import { CatalogProvider } from "./catalog-context";
import { CATALOG_UNAVAILABLE, CatalogProblem } from "./catalog-states";
import { ApiError } from "@/lib/api/errors";
import { FailuresTab } from "./failures-tab";
import { GroundedTab } from "./grounded-tab";
import { OVERVIEW_INTRO, OverviewTab } from "./overview-tab";
import { ProvenanceTab } from "./provenance-tab";
import { ResearchTab } from "./research-tab";
import { RetrievalTab } from "./retrieval-tab";

const catalog = catalogJson as unknown as EvalCatalog;

const render = (el: ReactElement, c: EvalCatalog = catalog) =>
  renderToStaticMarkup(<CatalogProvider catalog={c}>{el}</CatalogProvider>);
const textOf = (html: string) =>
  html
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&#x27;/g, "'")
    .replace(/&quot;/g, '"');

const NUM = /\d[\d,]*(?:\.\d+)?/g;
const UNITS: MetricUnit[] = ["ratio", "percent", "ms", "s", "usd", "count", "tokens"];

/** Every numeric token the catalog can legitimately produce, in any display format used here. */
function allowedTokens(c: EvalCatalog): Set<string> {
  const out = new Set<string>();
  const add = (s: string) => s.match(NUM)?.forEach((t) => out.add(t));
  const walk = (v: unknown): void => {
    if (typeof v === "number") {
      [String(v), formatNumber(v), formatNumber(v, 3), formatBytes(v)].forEach(add);
      UNITS.forEach((u) => {
        add(formatEvalValue(v, u));
        add(formatSigned(v, u));
      });
    } else if (typeof v === "string") {
      [v, v.slice(0, 10), v.slice(0, 12), formatDateTime(v)].forEach(add);
    } else if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === "object") Object.values(v).forEach(walk);
  };
  walk(c);
  // Metric names in column headers and the confidence level of every interval.
  ["1", "10", "50", "95"].forEach((t) => out.add(t));
  return out;
}

const TABS: [string, ReactElement][] = [
  ["overview", <OverviewTab key="o" catalog={catalog} />],
  ["retrieval", <RetrievalTab key="r" catalog={catalog} />],
  ["grounded", <GroundedTab key="g" catalog={catalog} />],
  ["research", <ResearchTab key="s" catalog={catalog} />],
  ["analytics", <AnalyticsTab key="a" catalog={catalog} />],
  ["failures", <FailuresTab key="f" catalog={catalog} ws="NORTHSTAR" />],
  ["provenance", <ProvenanceTab key="p" catalog={catalog} />],
];

describe("evaluation tabs", () => {
  const allowed = allowedTokens(catalog);

  it.each(TABS)("%s renders only numbers that come from the catalog", (_name, el) => {
    const tokens = textOf(render(el)).match(NUM) ?? [];
    expect(tokens.length).toBeGreaterThan(0);
    const stray = tokens.filter((t) => !allowed.has(t));
    expect(stray).toEqual([]);
  });

  it("always renders the caveats and the overview explanation", () => {
    const html = textOf(render(<OverviewTab catalog={catalog} />));
    expect(html).toContain(OVERVIEW_INTRO);
    for (const c of catalog.caveats) expect(html).toContain(c.text.slice(0, 40));
    const bare = { ...catalog, overview: { headline: [], phases: [] } };
    const html2 = textOf(render(<OverviewTab catalog={bare} />, bare));
    for (const c of catalog.caveats) expect(html2).toContain(c.text.slice(0, 40));
  });

  it("gives every metric a source disclosure", () => {
    const html = render(<GroundedTab catalog={catalog} />);
    const sources = html.match(/aria-label="Source: /g) ?? [];
    expect(sources.length).toBeGreaterThanOrEqual(catalog.grounded.metrics.length);
  });

  it("states the retrieval conclusion and keeps negative findings visible", () => {
    const text = textOf(render(<RetrievalTab catalog={catalog} />));
    expect(text).toContain("Negative finding");
    expect(text).toContain("Rejected");
    expect(text).toContain("Not adopted");
    for (const d of catalog.retrieval.decisions) expect(text).toContain(d.title);
  });

  it("states the research trade-off without implying research is always better", () => {
    const text = textOf(render(<ResearchTab catalog={catalog} />));
    expect(text).toContain("Research mode finds more relevant evidence, but costs more and takes longer.");
    expect(text).toContain("It is not better on every measure");
  });

  it("labels superseded analytics attempts", () => {
    const text = textOf(render(<AnalyticsTab catalog={catalog} />));
    expect(text.match(/Superseded/g)?.length ?? 0).toBeGreaterThanOrEqual(catalog.superseded.length);
  });
});

describe("catalog states", () => {
  it("explains that the catalog is development-only on 404 and on EVAL_CATALOG_UNAVAILABLE", () => {
    const e404 = renderToStaticMarkup(<CatalogProblem error={new ApiError(404, "NOT_FOUND", "x")} retry={() => {}} />);
    expect(textOf(e404)).toContain(CATALOG_UNAVAILABLE);
    const e503 = renderToStaticMarkup(
      <CatalogProblem error={new ApiError(503, "EVAL_CATALOG_UNAVAILABLE", "x")} retry={() => {}} />,
    );
    expect(textOf(e503)).toContain(CATALOG_UNAVAILABLE);
    const e500 = renderToStaticMarkup(<CatalogProblem error={new ApiError(500, "INTERNAL", "x")} retry={() => {}} />);
    expect(textOf(e500)).toContain("could not be loaded");
  });
});
