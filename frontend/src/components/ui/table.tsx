import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

export interface Column<T> {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  align?: "left" | "right";
  width?: string;
}

const INNER_CONTROLS = "a, button, input, select, textarea, summary, [role='button']";

/** True when the event started on an interactive element inside the row (not the row itself). */
function fromInnerControl(target: EventTarget, row: Element): boolean {
  if (!(target instanceof Element)) return false;
  const control = target.closest(INNER_CONTROLS);
  return control !== null && control !== row && row.contains(control);
}

/**
 * Data table with a caption (visually hidden unless `showCaption`), sticky-free header and
 * optional row activation. Rows with `onRowClick` are also reachable by keyboard (Enter/Space).
 */
export function Table<T>({
  columns,
  rows,
  rowKey,
  caption,
  showCaption = false,
  onRowClick,
  empty,
  density = "comfortable",
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  caption: string;
  showCaption?: boolean;
  onRowClick?: (row: T) => void;
  empty?: ReactNode;
  density?: "compact" | "comfortable";
}) {
  const pad = density === "compact" ? "px-3 py-1.5" : "px-4 py-2.5";
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface">
      <table className="w-full border-collapse text-left text-base">
        <caption className={showCaption ? "px-4 pt-3 pb-1 text-left text-sm text-muted" : "sr-only"}>{caption}</caption>
        <thead className="bg-surface-muted">
          <tr className="border-b border-border">
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                style={col.width ? { width: col.width } : undefined}
                className={cx(pad, "text-sm font-medium text-secondary", col.align === "right" && "text-right")}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-base text-muted">
                {empty ?? "Nothing to show yet."}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr
                key={rowKey(row)}
                tabIndex={onRowClick ? 0 : undefined}
                onClick={
                  onRowClick
                    ? (event) => {
                        if (fromInnerControl(event.target, event.currentTarget)) return;
                        onRowClick(row);
                      }
                    : undefined
                }
                onKeyDown={
                  onRowClick
                    ? (event) => {
                        // Keys pressed on a link or button inside the row keep their own behaviour.
                        if (event.target !== event.currentTarget) return;
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          onRowClick(row);
                        }
                      }
                    : undefined
                }
                className={cx(
                  "border-b border-border last:border-b-0",
                  onRowClick && "cursor-pointer hover:bg-surface-muted/60 focus-visible:outline-offset-[-2px]",
                )}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={cx(pad, "align-top text-primary", col.align === "right" && "text-right tabular-nums")}
                  >
                    {col.cell(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
