import type { RowField } from "@/lib/format";
import { cx } from "@/lib/cx";

/**
 * A spreadsheet or CSV passage as labelled fields (see `parseRowPassage`), instead of quoting
 * the raw "column: value; ..." text. `highlight` marks the field holding a cited span.
 */
export function RowFields({
  fields,
  highlight,
  className,
}: {
  fields: readonly RowField[];
  highlight?: { start: number; end: number } | null;
  className?: string;
}) {
  return (
    <dl className={cx("grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-4 gap-y-1 text-base", className)}>
      {fields.map((f) => {
        const marked = highlight != null && highlight.start < f.end && highlight.end > f.start;
        return (
          <div key={`${f.start}-${f.label}`} className="contents">
            <dt className="text-secondary">{f.label}</dt>
            <dd className={cx("min-w-0 break-words text-primary tabular-nums", marked && "evidence-mark rounded-sm")}>
              {marked && <span className="sr-only">Cited text: </span>}
              {f.value}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
