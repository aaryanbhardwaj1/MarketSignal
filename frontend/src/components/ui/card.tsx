import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

const PADDING = { none: "", sm: "p-4", md: "p-5" } as const;

/** Bordered surface. No shadow (overlays only get one). Use `<CardHeader>` for a titled card. */
export function Card({
  padding = "md",
  interactive = false,
  as: Tag = "div",
  className,
  children,
}: {
  padding?: keyof typeof PADDING;
  interactive?: boolean;
  as?: "div" | "article" | "li" | "section";
  className?: string;
  children: ReactNode;
}) {
  const surface = cx(
    "rounded-lg border border-border bg-surface",
    interactive && "transition-colors hover:border-border-strong hover:bg-surface-muted/40",
    className,
  );
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
