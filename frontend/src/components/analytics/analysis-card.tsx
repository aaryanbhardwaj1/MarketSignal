import Link from "next/link";
import type { Analysis } from "@/lib/api/contracts";
import { analysisHref } from "@/lib/routes";
import { populationLine, summaryView } from "@/lib/views/analytics";
import { ClaimTag } from "../ui/claim-tag";
import { AnalysisMiniVisual } from "./analysis-visual";

/**
 * The verified takeaway with its claim tag, or a plain note when it is withheld. Use
 * `as="span"` inside an element that is already a paragraph (e.g. a page header description).
 */
export function AnalysisSummary({ analysis, as: Tag = "p" }: { analysis: Analysis; as?: "p" | "span" }) {
  const summary = summaryView(analysis);
  if (summary.kind === "absent") return null;
  if (summary.kind === "withheld") {
    return <Tag className="text-sm text-muted">Summary withheld: its figures do not match the recomputed result.</Tag>;
  }
  return (
    <Tag className="text-base text-secondary">
      {summary.text} <ClaimTag type="derived" size="sm" className="ml-0.5" />
    </Tag>
  );
}

/**
 * One analysis on the Analytics list: business title, its verified takeaway, one small real
 * visual and the population and dataset it covers. The whole tile opens the detail page.
 */
export function AnalysisCard({ ws, analysis }: { ws: string; analysis: Analysis }) {
  const population = populationLine(analysis);
  return (
    <li className="group relative flex min-w-0 flex-col gap-3 rounded-lg border border-border bg-surface p-5 transition-colors duration-(--duration-fast) ease-standard hover:border-border-strong">
      <h3 className="text-md font-semibold text-primary">
        <Link
          href={analysisHref(ws, analysis.id)}
          className="rounded-sm after:absolute after:inset-0 after:rounded-lg after:content-[''] group-hover:text-accent-text"
        >
          {analysis.title}
        </Link>
      </h3>
      <AnalysisSummary analysis={analysis} />
      <div className="mt-1 flex-1">
        <AnalysisMiniVisual analysis={analysis} />
      </div>
      <p className="flex flex-wrap gap-x-2 border-t border-border pt-3 text-xs text-muted">
        {population && <span className="tabular-nums">{population}</span>}
        {population && <span aria-hidden>·</span>}
        <span>{analysis.provenance.source_title}</span>
      </p>
    </li>
  );
}
