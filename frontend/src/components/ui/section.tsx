import { useId, type ReactNode } from "react";

/** A titled page section: renders an h2 and owns the 32px section gap. */
export function Section({
  title,
  description,
  actions,
  id,
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  id?: string;
  children: ReactNode;
}) {
  const generated = useId();
  const headingId = `${id ?? generated}-heading`;
  return (
    <section id={id} aria-labelledby={headingId} className="mt-8 first:mt-0">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 id={headingId} className="text-md font-semibold text-primary">
            {title}
          </h2>
          {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
}
