import Link from "next/link";
import type { ChipToken } from "@/lib/citations";
import { evidenceViewerHref } from "@/lib/handles";
import { ResultChip } from "./result-chip";

const CHIP =
  "mx-0.5 inline-flex max-w-[16rem] items-center gap-1 rounded-full px-2 py-0.5 align-baseline text-[11px] font-medium leading-4 ring-1 ring-inset";

function chipLabel(title: string, locator: string): string {
  return locator ? `${title} · ${locator}` : title;
}

interface ChipTarget {
  handle: string;
  title: string;
  locator: string;
  child: string | null;
}

/** Where a chip links to; null for a canonical handle that has no matching citation card. */
function chipTarget(token: Exclude<ChipToken, { kind: "inference" | "result" }>): ChipTarget | null {
  if (token.kind === "alias") {
    const c = token.citation;
    return { handle: c.handle, title: c.source_title, locator: c.locator_label, child: null };
  }
  if (!token.card) return null;
  const c = token.card;
  return { handle: c.handle, title: c.source_title, locator: c.locator_label, child: c.anchor_child_id };
}

/** Chip for a resolved citation, a canonical handle without a card, or an `[inference]` tag. */
export function CitationChip({ token, ws }: { token: ChipToken; ws: string }) {
  if (token.kind === "inference") {
    return (
      <span
        title="Inference: reasoning beyond what the cited evidence states"
        className={`${CHIP} bg-violet-50 text-violet-700 ring-violet-600/20`}
      >
        Inference
      </span>
    );
  }

  if (token.kind === "result") {
    return <ResultChip ws={ws} resultId={token.resultId} result={token.ref} />;
  }

  const target = chipTarget(token);
  if (!target) {
    return (
      <span
        title="Unverified citation: this source is not among the answer's verified citations"
        className={`${CHIP} cursor-not-allowed bg-slate-100 text-slate-500 ring-slate-400/30`}
      >
        unverified
      </span>
    );
  }

  const { handle, title, locator, child } = target;
  const label = chipLabel(title || handle, locator);

  return (
    <Link
      href={evidenceViewerHref(ws, handle, child)}
      target="_blank"
      rel="noopener noreferrer"
      title={`${label}\n${handle}`}
      className={`${CHIP} bg-indigo-50 text-indigo-800 ring-indigo-600/20 hover:bg-indigo-100 focus-visible:outline-2 focus-visible:outline-indigo-600`}
    >
      <span className="truncate">{label}</span>
    </Link>
  );
}
