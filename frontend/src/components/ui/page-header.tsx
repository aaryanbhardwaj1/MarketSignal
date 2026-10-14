import Link from "next/link";
import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

export interface Crumb {
  label: string;
  href: string;
}

/**
 * Page identity: optional breadcrumb or `eyebrow` (small label above the title), h1 (24/28
 * semibold), a one-sentence description, a meta line, and actions on the right.
 */
export function PageHeader({
  title,
  description,
  actions,
  meta,
  breadcrumb,
  eyebrow,
  divider = true,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
  breadcrumb?: Crumb[];
  eyebrow?: ReactNode;
  /** Hairline under the header (default). Turn off when the next element draws its own edge. */
  divider?: boolean;
}) {
  return (
    <header className={cx("flex flex-col gap-3 pb-5", divider && "border-b border-border")}>
      {breadcrumb && breadcrumb.length > 0 && (
        <nav aria-label="Breadcrumb">
          <ol className="flex flex-wrap items-center gap-1.5 text-sm text-muted">
            {breadcrumb.map((crumb, index) => (
              <li key={`${crumb.href}-${index}`} className="flex items-center gap-1.5">
                {index > 0 && <span aria-hidden>/</span>}
                <Link
                  href={crumb.href}
                  className="rounded-sm transition-colors duration-(--duration-fast) ease-standard hover:text-primary"
                >
                  {crumb.label}
                </Link>
              </li>
            ))}
          </ol>
        </nav>
      )}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-reading">
          {eyebrow && <p className="mb-1 text-xs font-medium text-muted">{eyebrow}</p>}
          <h1 className="text-xl font-semibold text-primary">{title}</h1>
          {description && <p className="mt-1.5 text-base text-secondary">{description}</p>}
          {meta && <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-muted">{meta}</div>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2 sm:pt-0.5">{actions}</div>}
      </div>
    </header>
  );
}
