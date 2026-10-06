"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ResultRef } from "@/lib/citations";
import { ResultCard } from "./result-card";

const CHIP =
  "mx-0.5 inline-flex max-w-[18rem] items-center gap-1 rounded-full px-2 py-0.5 align-baseline text-[11px] font-medium leading-4 ring-1 ring-inset bg-teal-50 text-teal-900 ring-teal-600/30 hover:bg-teal-100 focus-visible:outline-2 focus-visible:outline-teal-700";

function ResultDialog({
  ws,
  resultId,
  summary,
  onClose,
}: {
  ws: string;
  resultId: string;
  summary: string;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Computed result${summary ? `: ${summary}` : ""}`}
        className="mt-12 w-full max-w-2xl rounded-lg border border-teal-200 bg-slate-50 p-4 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-2 flex items-start justify-between gap-3">
          <h2 className="text-sm font-semibold text-slate-900">∑ Computed result{summary ? ` · ${summary}` : ""}</h2>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="rounded px-2 py-0.5 text-xs font-medium text-slate-600 ring-1 ring-slate-300 hover:bg-white"
          >
            Close
          </button>
        </div>
        <ResultCard ws={ws} resultId={resultId} />
      </div>
    </div>,
    document.body,
  );
}

/** Chip for a computed result: visually distinct from evidence chips; opens the result card. */
export function ResultChip({ ws, resultId, result }: { ws: string; resultId: string; result: ResultRef | null }) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const summary = result?.summary ?? "";
  const close = useCallback(() => {
    setOpen(false);
    buttonRef.current?.focus();
  }, []);
  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        title={`Computed result${summary ? `: ${summary}` : ""}\nDeterministic calculation, not a quoted source`}
        className={CHIP}
        onClick={() => setOpen(true)}
      >
        <span aria-hidden>∑</span>
        <span className="truncate">computed{summary ? ` · ${summary}` : ""}</span>
      </button>
      {open && <ResultDialog ws={ws} resultId={resultId} summary={summary} onClose={close} />}
    </>
  );
}
