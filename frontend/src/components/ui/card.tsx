import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

const PADDING = { none: "", sm: "p-4", md: "p-5" } as const;

/**
 * Bordered surface. No shadow (overlays only get one).
 * `title`/`actions` are a deprecated shorthand for `<CardHeader>` plus a padded body.
 */
export function Card({
  padding = "md",
  interactive = false,
  as: Tag = "div",
  className,
  title,
  actions,
  children,
}: {
  padding?: keyof typeof PADDING;
  interactive?: boolean;
  as?: "div" | "article" | "li" | "section";
  className?: string;
  /** @deprecated Use `<CardHeader title=...>` inside `<Card padding="none">`. */
  title?: ReactNode;
  /** @deprecated Use `<CardHeader actions=...>`. */
  actions?: ReactNode;
  children: ReactNode;
}) {
  const surface = cx(
    "rounded-lg border border-border bg-surface",
    interactive && "transition-colors hover:border-border-strong hover:bg-surface-muted/40",
    className,
  );
  if (title || actions) {
    return (
      <Tag className={surface}>
        <CardHeader title={title} actions={actions} />
        <div className={PADDING[padding]}>{children}</div>
      </Tag>
    );
  }
  return <Tag className={cx(surface, PADDING[padding])}>{children}</Tag>;
}

export function CardHeader({
  title,
  meta,
  actions,
}: {
  title?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-5 py-3">
      <div className="min-w-0">
        {title && <h3 className="text-base font-semibold text-primary">{title}</h3>}
        {meta && <div className="mt-0.5 text-sm text-muted">{meta}</div>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

/** @deprecated Import from `./page-header`. Re-exported so older pages keep building. */
export { PageHeader } from "./page-header";
