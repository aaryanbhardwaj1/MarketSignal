import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

const WIDTHS = {
  reading: "max-w-reading",
  content: "max-w-content",
  wide: "max-w-wide",
} as const;

/** Centred page column with the standard gutter (24px, 16px under 768px). */
export function PageContainer({
  width = "content",
  className,
  children,
}: {
  width?: keyof typeof WIDTHS;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cx("mx-auto w-full px-4 py-6 md:px-6 md:py-8", WIDTHS[width], className)}>
      {children}
    </div>
  );
}
