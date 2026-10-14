import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import { SectionHeader } from "@/components/ui/section-header";

/** One gallery section with an anchor, a hairline above and a short description. */
export function GallerySection({ id, title, description, children }: { id: string; title: string; description?: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-heading`} className="scroll-mt-6 border-t border-border pt-8">
      <SectionHeader id={`${id}-heading`} title={title} description={description} className="mb-5" />
      {children}
    </section>
  );
}

/** A labelled specimen inside a section. */
export function Block({ title, className, children }: { title: string; className?: string; children: ReactNode }) {
  return (
    <div className={cx("flex min-w-0 flex-col gap-3", className)}>
      <p className="text-xs font-medium text-muted">{title}</p>
      {children}
    </div>
  );
}

export function Grid({ cols = 3, children }: { cols?: 2 | 3 | 4; children: ReactNode }) {
  const c = { 2: "md:grid-cols-2", 3: "md:grid-cols-3", 4: "md:grid-cols-2 lg:grid-cols-4" }[cols];
  return <div className={cx("grid items-start gap-x-6 gap-y-8", c)}>{children}</div>;
}

/** Every chart and figure in the gallery is illustrative; this label makes that impossible to miss. */
export function SampleNote() {
  return <p className="text-xs text-muted">Sample data for illustration only. Not a measurement.</p>;
}
