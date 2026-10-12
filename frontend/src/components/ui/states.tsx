import type { ReactNode } from "react";
import { describeError } from "@/lib/api/errors";
import { cx } from "@/lib/cx";
import { errorMessage } from "@/lib/labels";
import { Card } from "./card";
import { DevDetails } from "./disclosure";

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center rounded-lg border border-dashed border-border-strong bg-surface px-6 py-10 text-center">
      <p className="text-md font-semibold text-primary">{title}</p>
      {description && <p className="mt-1 max-w-reading text-base text-secondary">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/**
 * Plain-language failure with an optional retry; any code goes only in "Technical details".
 * Pass `error` (a query error) to derive the message and code consistently on every page;
 * an explicit `description` or `devDetail` overrides the derived one.
 */
export function ErrorState({
  title,
  description,
  error,
  retry,
  devDetail,
}: {
  title: string;
  description?: ReactNode;
  error?: unknown;
  retry?: () => void;
  devDetail?: string;
}) {
  const code = error !== undefined ? describeError(error).code : null;
  const body = description ?? (code ? errorMessage(code).label : null);
  const detail = devDetail ?? code ?? undefined;
  return (
    <div role="alert" className="rounded-lg border border-danger/25 bg-danger-subtle px-4 py-3.5">
      <p className="text-base font-semibold text-danger">{title}</p>
      {body && <div className="mt-0.5 text-base text-primary">{body}</div>}
      {retry && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={retry}
            className="inline-flex h-7 items-center rounded-md border border-border-strong bg-surface px-2.5 text-sm font-medium text-primary hover:bg-surface-muted"
          >
            Try again
          </button>
        </div>
      )}
      {detail && (
        <div className="mt-2">
          <DevDetails>{detail}</DevDetails>
        </div>
      )}
    </div>
  );
}

/** Placeholder bars while content loads. Decorative: pair with `LoadingRegion` for screen readers. */
export function Skeleton({ lines = 3, height, className }: { lines?: number; height?: string; className?: string }) {
  if (height) {
    return <div aria-hidden className={cx("ms-skeleton rounded-md bg-surface-sunken", className)} style={{ height }} />;
  }
  return (
    <div aria-hidden className={cx("flex flex-col gap-2", className)}>
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="ms-skeleton h-3 rounded-sm bg-surface-sunken"
          style={{ width: i === lines - 1 && lines > 1 ? "60%" : "100%" }}
        />
      ))}
    </div>
  );
}

/** Announces loading politely and shows skeleton content (or children) meanwhile. */
export function LoadingRegion({ label, lines = 3, children }: { label: string; lines?: number; children?: ReactNode }) {
  return (
    <div role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      {children ?? <Skeleton lines={lines} />}
    </div>
  );
}

/**
 * Loading placeholder for a grid of summary cards: `count` cards of `lines` skeleton bars, announced
 * once to screen readers via `label`. `columns` adds responsive grid-cols classes (single column if omitted).
 */
export function CardGridSkeleton({
  label,
  count = 3,
  lines = 3,
  columns,
  gap = "md",
  padding = "sm",
}: {
  label: string;
  count?: number;
  lines?: number;
  columns?: string;
  gap?: "sm" | "md";
  padding?: "sm" | "md";
}) {
  return (
    <LoadingRegion label={label}>
      <div className={cx("grid", gap === "sm" ? "gap-3" : "gap-4", columns)}>
        {Array.from({ length: count }, (_, i) => (
          <Card key={i} padding={padding}>
            <Skeleton lines={lines} />
          </Card>
        ))}
      </div>
    </LoadingRegion>
  );
}
