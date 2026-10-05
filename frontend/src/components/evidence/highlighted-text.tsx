"use client";

import { useEffect, useRef } from "react";
import { segmentHighlight, type ActiveSpan } from "@/lib/highlight";

/** Parent text rendered as plain text with the active child span wrapped in <mark>. */
export function HighlightedText({ text, span }: { text: string; span: ActiveSpan | null }) {
  const markRef = useRef<HTMLElement>(null);
  const segments = segmentHighlight(text, span?.charStart, span?.charEnd);
  const mismatch =
    segments.valid && span?.expectedText != null && span.expectedText !== segments.mark;

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [span?.childId, span?.charStart, span?.charEnd]);

  return (
    <div className="flex flex-col gap-2">
      <div
        aria-label="Parent evidence text"
        className="max-h-[32rem] overflow-y-auto whitespace-pre-wrap break-words rounded-lg border border-slate-200 bg-slate-50 p-4 text-[0.9rem] leading-relaxed text-slate-800"
      >
        {segments.before}
        {segments.valid && (
          <mark ref={markRef} className="evidence-mark">
            {segments.mark}
          </mark>
        )}
        {segments.after}
      </div>
      {span && !segments.valid && (
        <p className="text-xs text-amber-700">
          Span [{span.charStart}, {span.charEnd}) is outside the parent text; nothing highlighted.
        </p>
      )}
      {mismatch && (
        <p role="alert" className="text-xs text-red-700">
          Integrity warning: the text at [{span?.charStart}, {span?.charEnd}) differs from the
          server&apos;s highlight text.
        </p>
      )}
    </div>
  );
}
