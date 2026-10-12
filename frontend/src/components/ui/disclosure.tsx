import type { ReactNode } from "react";

const CHEVRON = (
  <svg aria-hidden viewBox="0 0 16 16" className="h-3.5 w-3.5 shrink-0 text-muted transition-transform group-open:rotate-90" fill="none" stroke="currentColor" strokeWidth="1.75">
    <path d="m6 4 4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

/** Native details/summary disclosure (keyboard and screen-reader support built in). */
export function Disclosure({
  summary,
  defaultOpen = false,
  children,
}: {
  summary: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  return (
    <details open={defaultOpen} className="group rounded-lg border border-border bg-surface">
      <summary className="flex cursor-pointer list-none items-center gap-2 rounded-lg px-4 py-2.5 text-base font-medium text-primary hover:bg-surface-muted/60 [&::-webkit-details-marker]:hidden">
        {CHEVRON}
        {summary}
      </summary>
      <div className="border-t border-border px-4 py-3">{children}</div>
    </details>
  );
}

function pretty(data: unknown): string {
  if (typeof data === "string") return data;
  try {
    return JSON.stringify(data, null, 2) ?? String(data);
  } catch {
    return String(data);
  }
}

/**
 * "Technical details": the only place raw codes, handles and ids appear on business pages.
 * `data` is pretty-printed as JSON in mono; `children` render above it.
 */
export function DevDetails({ data, summary = "Technical details", children }: { data?: unknown; summary?: string; children?: ReactNode }) {
  return (
    <details className="group text-sm">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-sm text-muted hover:text-primary [&::-webkit-details-marker]:hidden">
        {CHEVRON}
        {summary}
      </summary>
      <div className="mt-2 rounded-md border border-border bg-surface-muted p-3">
        {children && <div className="break-words font-mono text-xs text-secondary">{children}</div>}
        {data !== undefined && (
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all font-mono text-xs text-secondary">{pretty(data)}</pre>
        )}
      </div>
    </details>
  );
}
