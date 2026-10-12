"use client";

import { describeResult } from "@/components/analytics/result-summary";
import { CiteChip } from "@/components/ui/cite-chip";
import { useOptionalEvidenceDrawer } from "@/components/evidence/drawer-context";
import type { AnalyticsResultSummary } from "@/lib/api/contracts";
import type { ResultRef } from "@/lib/citations";
import { COMPUTED_FIGURE } from "./answer-evidence";
import { useChipNumbering } from "./citation-numbering";

/** Plain-language name of a cited result from its stored machine summary (never the raw summary); null if none. */
export function resultChipLabel(result: ResultRef | null): string | null {
  // Only a stored machine summary ("aggregate ; mean(nps) ; by region ; …") names a metric.
  if (!result?.summary || !result.summary.includes(" ; ")) return null;
  const { title } = describeResult({
    tool: (result.op || "aggregate") as AnalyticsResultSummary["tool"],
    summary: result.summary,
    metrics: [],
  });
  return title;
}

/**
 * Chip for a computed result: visually distinct from evidence chips. Inside a workspace page it
 * opens the result in the evidence drawer; outside one (static previews) it is plain,
 * non-interactive text.
 */
export function ResultChip({ ws, resultId, result }: { ws: string; resultId: string; result: ResultRef | null }) {
  const drawer = useOptionalEvidenceDrawer();
  const numbering = useChipNumbering();
  const title = resultChipLabel(result);
  if (drawer) {
    // CiteChip already announces the kind ("Computed … N: …"), so pass only the figure's name.
    return (
      <CiteChip
        kind="result"
        index={numbering?.resultNumber.get(resultId) ?? 1}
        label={title ?? "calculated from a workspace dataset"}
        onOpen={() => drawer.openResult(resultId)}
      />
    );
  }
  const label = title ? `${COMPUTED_FIGURE}: ${title}` : COMPUTED_FIGURE;
  return (
    <span
      data-workspace={ws}
      title={`${label}. A calculation over a dataset, not a quoted source.`}
      className="mx-0.5 inline-flex max-w-72 items-center gap-1 rounded-sm border border-cite-result/20 bg-cite-result-bg px-1.5 align-baseline text-xs font-medium text-cite-result"
    >
      <span className="truncate">{label}</span>
    </span>
  );
}
