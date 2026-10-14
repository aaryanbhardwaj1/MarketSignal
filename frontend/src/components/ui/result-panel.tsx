import type { ReactNode } from "react";
import { tableLabel } from "@/lib/format";
import { KeyValueList } from "./key-value";

/** "From <title> · Version N · <table in words>", omitting a table that repeats the title or is unknown. */
export function provenanceLine({ sourceTitle, version, table }: { sourceTitle: string; version: string | number; table: string }): string {
  const plain = /^[-–\s]*$/.test(table) ? "" : tableLabel(table);
  const repeats = plain !== "" && sourceTitle.toLowerCase().includes(plain.toLowerCase());
  return [`From ${sourceTitle}`, `Version ${version}`, plain && !repeats ? plain : null].filter(Boolean).join(" · ");
}

/**
 * A computed analytics result. Teal left rule plus a "Computed" label, so it never reads as an
 * evidence passage. Provenance names the dataset, version and table the figure came from; the
 * stored table name is shown in words. `denominator` should state the base with its total
 * ("68 of 600 records"), so a figure never appears without one.
 */
export function ResultPanel({
  title,
  value,
  unit,
  denominator,
  filters,
  groupBy,
  provenance,
  children,
  headingLevel = 3,
}: {
  title: string;
  value?: ReactNode;
  unit: string;
  denominator?: { label: string; value: ReactNode };
  filters?: string[];
  groupBy?: string[];
  provenance: { sourceTitle: string; sourceCode: string; version: string | number; table: string };
  children?: ReactNode;
  /** Heading level of the title (3 by default; 4 when nested under an h3). */
  headingLevel?: 3 | 4;
}) {
  const details = [
    ...(denominator ? [{ label: denominator.label, value: denominator.value }] : []),
    ...(filters && filters.length > 0 ? [{ label: "Filters", value: filters.join("; ") }] : []),
    ...(groupBy && groupBy.length > 0 ? [{ label: "Grouped by", value: groupBy.join(", ") }] : []),
  ];
  const Heading = headingLevel === 4 ? "h4" : "h3";
  return (
    <section className="rounded-lg border border-border border-l-2 border-l-cite-result bg-surface px-4 py-3.5">
      <p className="text-xs font-medium text-cite-result">Computed</p>
      <Heading className="mt-0.5 text-base font-semibold text-primary">{title}</Heading>
      {value != null && (
        <p className="mt-2 flex items-baseline gap-1 text-xl font-semibold tabular-nums text-primary">
          {value}
          <span className="text-sm font-medium text-muted">{unit}</span>
        </p>
      )}
      {details.length > 0 && (
        <div className="mt-3">
          <KeyValueList items={details} columns={details.length > 1 ? 2 : 1} />
        </div>
      )}
      {children && <div className="mt-3">{children}</div>}
      <p className="mt-3 border-t border-border pt-2.5 text-xs text-muted">
        {provenanceLine(provenance)}
      </p>
    </section>
  );
}
