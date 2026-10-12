import type { ReactNode } from "react";
import { KeyValueList } from "./key-value";

/**
 * A computed analytics result. Teal left rule plus a "Computed" label, so it never reads as an
 * evidence passage. Provenance names the dataset, version and table the figure came from.
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
}: {
  title: string;
  value?: ReactNode;
  unit: string;
  denominator?: { label: string; value: ReactNode };
  filters?: string[];
  groupBy?: string[];
  provenance: { sourceTitle: string; sourceCode: string; version: string | number; table: string };
  children?: ReactNode;
}) {
  const details = [
    ...(denominator ? [{ label: denominator.label, value: denominator.value }] : []),
    ...(filters && filters.length > 0 ? [{ label: "Filters", value: filters.join("; ") }] : []),
    ...(groupBy && groupBy.length > 0 ? [{ label: "Grouped by", value: groupBy.join(", ") }] : []),
  ];
  return (
    <section className="rounded-lg border border-border border-l-[3px] border-l-cite-result bg-surface p-4">
      <p className="text-xs font-medium text-cite-result">Computed</p>
      <h3 className="mt-0.5 text-base font-semibold text-primary">{title}</h3>
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
      <p className="mt-3 border-t border-border pt-2 text-xs text-muted" data-source-code={provenance.sourceCode}>
        From {provenance.sourceTitle} · Version {provenance.version} · Table {provenance.table}
      </p>
    </section>
  );
}
