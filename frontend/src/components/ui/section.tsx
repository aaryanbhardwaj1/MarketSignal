import { useId, type ReactNode } from "react";
import { SectionHeader } from "./section-header";

/** A titled page section: renders an h2 (via `SectionHeader`) and owns the 32px section gap. */
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
      <SectionHeader id={headingId} title={title} description={description} action={actions} className="mb-3" />
      {children}
    </section>
  );
}
