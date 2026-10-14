import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

const PADDING = { none: "", sm: "p-4", md: "p-5" } as const;

/**
 * `default` is a white surface with a hairline (no heavy chrome); `raised` adds the soft raised
 * shadow for the one element that should lift; `plain` is just a section, no border or fill,
 * for content that hierarchy and whitespace already separate. Use `<CardHeader>` for a titled card.
 */
export type CardVariant = "default" | "raised" | "plain";

const VARIANT: Record<CardVariant, string> = {
  default: "rounded-lg border border-border bg-surface",
  raised: "rounded-lg border border-border bg-raised shadow-raised",
  plain: "",
};

export function Card({
  padding = "md",
  interactive = false,
  variant = "default",
  as: Tag = "div",
  className,
  children,
}: {
  padding?: keyof typeof PADDING;
  interactive?: boolean;
  variant?: CardVariant;
  as?: "div" | "article" | "li" | "section";
  className?: string;
  children: ReactNode;
}) {
  const surface = cx(
    VARIANT[variant],
    interactive &&
      "transition-colors duration-(--duration-fast) ease-standard hover:border-border-strong hover:bg-surface-muted/50",
    className,
  );
  return <Tag className={cx(surface, variant === "plain" ? "" : PADDING[padding])}>{children}</Tag>;
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
