"use client";

import { useEffect, useRef } from "react";
import { segmentHighlight, type ActiveSpan } from "@/lib/highlight";

/** Passage rendered as plain text with the cited span wrapped in <mark>. */
export function HighlightedText({ text, span }: { text: string; span: ActiveSpan | null }) {
  const markRef = useRef<HTMLElement>(null);
  const segments = segmentHighlight(text, span?.charStart, span?.charEnd);
  const mismatch =
    segments.valid && span?.expectedText != null && span.expectedText !== segments.mark;

  useEffect(() => {
    const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    markRef.current?.scrollIntoView?.({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
  }, [span?.childId, span?.charStart, span?.charEnd]);

  return (
    <div className="flex flex-col gap-2">
      <div
        role="region"
        tabIndex={0}
        aria-label="Evidence passage text"
        className="max-h-96 overflow-y-auto whitespace-pre-wrap break-words rounded-md border border-border bg-surface-muted px-4 py-3 text-base leading-relaxed text-primary"
      >
        {segments.before}
        {segments.valid && (
          <mark ref={markRef} className="evidence-mark">
            <span className="sr-only">Cited text: </span>
            {segments.mark}
          </mark>
        )}
        {segments.after}
      </div>
      {span && !segments.valid && (
        <p className="text-sm text-warn">The cited part could not be located in this passage, so nothing is highlighted.</p>
      )}
      {mismatch && (
        <p role="alert" className="text-sm text-danger">
          The highlighted text differs from the cited text. Check the passage before relying on it.
        </p>
      )}
    </div>
  );
}
