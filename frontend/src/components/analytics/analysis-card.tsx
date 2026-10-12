import Link from "next/link";
import type { Analysis } from "@/lib/api/contracts";
import { formatNumber } from "@/lib/format";
import { Badge } from "../ui/badge";
import { Card } from "../ui/card";
import { analysisHeadline, analysisState, categoryLabel, coverageLine, scopeLine } from "./analysis-format";
import { analysisHref } from "@/lib/routes";

/** Summary card for one named analysis; the headline figure only appears when recomputed. */
export function AnalysisCard({ ws, analysis }: { ws: string; analysis: Analysis }) {
  const headline = analysisHeadline(analysis);
  const state = analysisState(analysis);
  const groups = analysis.rows.length;
  return (
    <Card as="li" padding="none" interactive className="min-w-0">
      <Link href={analysisHref(ws, analysis.id)} className="flex h-full flex-col rounded-lg p-4">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-base font-semibold text-primary">{analysis.title}</h3>
          <Badge tone="neutral">{categoryLabel(analysis.category)}</Badge>
        </div>
        <p className="mt-1 text-sm text-muted">{scopeLine(analysis)}</p>
        <div className="mt-4 flex-1 border-l-[3px] border-l-cite-result pl-3">
          {headline ? (
            <>
              <p className="truncate text-sm text-secondary" title={headline.label}>
                {headline.label}
              </p>
              <p className="mt-0.5 text-lg font-semibold tabular-nums text-primary">{headline.display}</p>
              {headline.context && <p className="text-sm text-muted">{headline.context}</p>}
            </>
          ) : (
            <p className="text-sm text-secondary">
              <span className="font-medium text-primary">{state.label}.</span> {state.message}
            </p>
          )}
        </div>
        <p className="mt-4 flex flex-wrap gap-x-3 border-t border-border pt-2 text-xs text-muted">
          {analysis.op === "filter_rows" ? (
            <span>{`${formatNumber(groups)} records listed`}</span>
          ) : (
            <>
              {coverageLine(analysis) && <span>{coverageLine(analysis)}</span>}
              {headline && groups > 1 && <span>{`${formatNumber(groups)} groups in full result`}</span>}
            </>
          )}
        </p>
      </Link>
    </Card>
  );
}
