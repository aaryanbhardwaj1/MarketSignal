"use client";

import Link from "next/link";
import { CiteChip, InferenceTag } from "@/components/ui/cite-chip";
import { useOptionalEvidenceDrawer } from "@/components/evidence/drawer-context";
import type { ChipToken } from "@/lib/citations";
import { evidenceViewerHref } from "@/lib/handles";
import { useChipNumbering } from "./citation-numbering";
import { ResultChip } from "./result-chip";

const FALLBACK_CHIP =
  "mx-0.5 inline-flex max-w-64 items-center gap-1 rounded-sm border px-1.5 align-baseline text-xs font-medium";

function chipLabel(title: string, locator: string): string {
  return locator ? `${title} · ${locator}` : title;
}

interface ChipTarget {
  handle: string;
  title: string;
  locator: string;
  child: string | null;
  charStart: number | null;
  charEnd: number | null;
  /** Number from a run-local alias (`E3` → 3), used while a draft streams. */
  aliasNumber: number | null;
}

/** Where a chip points; null for a canonical handle that has no matching citation card. */
function chipTarget(token: Exclude<ChipToken, { kind: "inference" | "result" }>): ChipTarget | null {
  if (token.kind === "alias") {
    const c = token.citation;
    const n = Number(token.alias.slice(1));
    return {
      handle: c.handle,
      title: c.source_title,
      locator: c.locator_label,
      child: null,
      charStart: null,
      charEnd: null,
      aliasNumber: Number.isInteger(n) ? n : null,
    };
  }
  if (!token.card) return null;
  const c = token.card;
  return {
    handle: c.handle,
    title: c.source_title,
    locator: c.locator_label,
    child: c.anchor_child_id,
    charStart: c.char_start,
    charEnd: c.char_end,
    aliasNumber: null,
  };
}

/**
 * Chip for a resolved citation, a canonical handle without a card, or an `[inference]` tag.
 * Inside a workspace page it opens the evidence drawer at the cited passage.
 */
export function CitationChip({ token, ws }: { token: ChipToken; ws: string }) {
  const drawer = useOptionalEvidenceDrawer();
  const numbering = useChipNumbering();

  if (token.kind === "inference") return <InferenceTag />;
  if (token.kind === "result") return <ResultChip ws={ws} resultId={token.resultId} result={token.ref} />;

  const target = chipTarget(token);
  if (!target) {
    return (
      <span
        title="This source is not among the answer's verified citations"
        className={`${FALLBACK_CHIP} cursor-not-allowed border-dashed border-border-strong text-muted`}
      >
        not verified
      </span>
    );
  }

  const label = chipLabel(target.title || "Evidence passage", target.locator);
  if (drawer) {
    const index = numbering?.evidenceNumber.get(target.handle) ?? target.aliasNumber ?? 0;
    return (
      <CiteChip
        kind="evidence"
        index={index}
        label={label}
        onOpen={() =>
          drawer.openEvidence({
            handle: target.handle,
            childId: target.child,
            charStart: target.charStart ?? undefined,
            charEnd: target.charEnd ?? undefined,
          })
        }
      />
    );
  }

  return (
    <Link
      href={evidenceViewerHref(ws, target.handle, target.child)}
      title={label}
      className={`${FALLBACK_CHIP} border-cite-evidence/20 bg-cite-evidence-bg text-cite-evidence hover:border-cite-evidence/50`}
    >
      <span className="truncate">{label}</span>
    </Link>
  );
}
