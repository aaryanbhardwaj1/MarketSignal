import Link from "next/link";
import type { ReactNode } from "react";

export interface Crumb {
  label: string;
  href: string;
}

/** Page title block: optional breadcrumb, h1, description, meta line and actions. */
export function PageHeader({
  title,
  description,
  actions,
  meta,
  breadcrumb,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
  breadcrumb?: Crumb[];
  /** @deprecated Raw eyebrows (workspace codes) are no longer shown. Accepted and ignored. */
  eyebrow?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-3 border-b border-border pb-5">
      {breadcrumb && breadcrumb.length > 0 && (
        <nav aria-label="Breadcrumb">
          <ol className="flex flex-wrap items-center gap-1.5 text-sm text-muted">
            {breadcrumb.map((crumb, index) => (
              <li key={`${crumb.href}-${index}`} className="flex items-center gap-1.5">
                {index > 0 && <span aria-hidden>/</span>}
                <Link href={crumb.href} className="rounded-sm hover:text-primary hover:underline">
                  {crumb.label}
                </Link>
              </li>
            ))}
          </ol>
        </nav>
      )}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-reading">
          <h1 className="text-xl font-semibold tracking-tight text-primary">{title}</h1>
          {description && <p className="mt-1.5 text-base text-secondary">{description}</p>}
          {meta && <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-muted">{meta}</div>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}
