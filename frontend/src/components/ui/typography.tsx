import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

const HEADING = {
  1: "text-xl font-semibold tracking-tight",
  2: "text-md font-semibold",
  3: "text-base font-semibold",
} as const;

export function Heading({
  level,
  id,
  className,
  children,
}: {
  level: 1 | 2 | 3;
  id?: string;
  className?: string;
  children: ReactNode;
}) {
  const Tag = `h${level}` as const;
  return (
    <Tag id={id} className={cx("text-primary", HEADING[level], className)}>
      {children}
    </Tag>
  );
}

const TONES = { default: "text-primary", secondary: "text-secondary", muted: "text-muted" } as const;
const SIZES = { xs: "text-xs", sm: "text-sm", base: "text-base" } as const;

export function Text({
  tone = "default",
  size = "base",
  as: Tag = "p",
  className,
  children,
}: {
  tone?: keyof typeof TONES;
  size?: keyof typeof SIZES;
  as?: "p" | "span" | "div";
  className?: string;
  children: ReactNode;
}) {
  return <Tag className={cx(TONES[tone], SIZES[size], className)}>{children}</Tag>;
}
