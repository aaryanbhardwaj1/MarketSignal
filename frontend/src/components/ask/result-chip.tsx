"use client";

import { CiteChip } from "@/components/ui/cite-chip";
import { useOptionalEvidenceDrawer } from "@/components/evidence/drawer-context";
import type { ResultRef } from "@/lib/citations";
import { useChipNumbering } from "./citation-numbering";

/**
 * Chip for a computed result: visually distinct from evidence chips. Inside a workspace page it
 * opens the result in the evidence drawer; outside one (e.g. static previews) it is inert.
 */
export function ResultChip({ ws, resultId, result }: { ws: string; resultId: string; result: ResultRef | null }) {
  const drawer = useOptionalEvidenceDrawer();
  const numbering = useChipNumbering();
  const summary = result?.summary ?? "";
  const label = `Computed result${summary ? `: ${summary}` : ""}`;
  if (drawer) {
    return (
      <CiteChip
        kind="result"
        index={numbering?.resultNumber.get(resultId) ?? 1}
        label={label}
        onOpen={() => drawer.openResult(resultId)}
      />
    );
  }
  return (
    <button
      type="button"
      data-workspace={ws}
      title={`${label}. A calculation over a dataset, not a quoted source.`}
      className="mx-0.5 inline-flex max-w-72 items-center gap-1 rounded-sm border border-cite-result/20 bg-cite-result-bg px-1.5 align-baseline text-xs font-medium text-cite-result"
    >
      <span className="truncate">computed{summary ? ` · ${summary}` : ""}</span>
    </button>
  );
}
