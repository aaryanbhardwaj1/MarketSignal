"use client";

import { ChevronRight } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { cx } from "@/lib/cx";
import { Collapse } from "@/components/motion/collapse";

function Chevron({ open }: { open: boolean }) {
  return (
    <ChevronRight
      aria-hidden
      size={14}
      strokeWidth={1.75}
      className={cx(
        "shrink-0 text-muted transition-transform duration-(--duration-base) ease-standard motion-reduce:transition-none",
        open && "rotate-90",
      )}
    />
  );
}

/**
 * Disclosure: a button with `aria-expanded` that animates its content open (`Collapse`) and
 * rotates its chevron. Closed content is inert, so it leaves the tab order.
 * `variant="plain"` matches the quiet "Technical details" style, for use beside it.
 */
export function Disclosure({
  summary,
  defaultOpen = false,
  variant = "card",
  children,
}: {
  summary: ReactNode;
  defaultOpen?: boolean;
  variant?: "card" | "plain";
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  const trigger = (className: string) => (
    <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen((v) => !v)} className={className}>
      <Chevron open={open} />
      {summary}
    </button>
  );
  if (variant === "plain") {
    return (
      <div className="text-sm">
        {trigger(
          "inline-flex items-center gap-1.5 rounded-sm text-muted transition-colors duration-(--duration-fast) ease-standard hover:text-primary",
        )}
        <Collapse open={open} id={id}>
          <div className="pt-2">{children}</div>
        </Collapse>
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-border bg-surface">
      {trigger(
        "flex w-full items-center gap-2 rounded-lg px-4 py-2.5 text-left text-base font-medium text-primary transition-colors duration-(--duration-fast) ease-standard hover:bg-surface-muted/60",
      )}
      <Collapse open={open} id={id}>
        <div className="border-t border-border px-4 py-3">{children}</div>
      </Collapse>
    </div>
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
 * `data` is pretty-printed as JSON in mono; `children` render above it. Stays a native
 * details/summary so its content is findable with the browser's find-in-page.
 */
export function DevDetails({ data, summary = "Technical details", children }: { data?: unknown; summary?: string; children?: ReactNode }) {
  return (
    <details className="group text-sm">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-sm text-muted transition-colors duration-(--duration-fast) ease-standard hover:text-primary [&::-webkit-details-marker]:hidden">
        <ChevronRight
          aria-hidden
          size={14}
          strokeWidth={1.75}
          className="shrink-0 transition-transform duration-(--duration-base) ease-standard group-open:rotate-90 motion-reduce:transition-none"
        />
        {summary}
      </summary>
      <div className="mt-2 rounded-md border border-border bg-sunken/60 p-3">
        {children && <div className="break-words font-mono text-xs text-secondary">{children}</div>}
        {data !== undefined && (
          <pre className="ms-scroll max-h-80 overflow-auto whitespace-pre-wrap break-all font-mono text-xs text-secondary">{pretty(data)}</pre>
        )}
      </div>
    </details>
  );
}
