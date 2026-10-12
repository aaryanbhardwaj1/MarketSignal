"use client";

import Link from "next/link";
import { formatDate, formatNumber } from "@/lib/format";
import { sourceClass, sourceType } from "@/lib/labels";
import { filterLibraryRows, versionLabel, type LibraryFilters, type LibraryRow } from "@/lib/library-filters";
import { libraryStatusLabel, versionStatusLabel } from "@/lib/status";
import { Button } from "../ui/button";
import { EmptyState } from "../ui/states";
import { StatusIndicator } from "../ui/status-indicator";
import { Table, type Column } from "../ui/table";
import { sourceHref } from "@/lib/routes";

/** True when every row says the same thing in a column, so the column would tell the reader nothing. */
function uniform(rows: readonly LibraryRow[], value: (row: LibraryRow) => string): boolean {
  return new Set(rows.map(value)).size <= 1;
}

function statusOf(row: LibraryRow) {
  return row.isCurrent ? versionStatusLabel(row.status) : libraryStatusLabel(row.bucket);
}

/**
 * Status, version and updated date only appear when they vary: a library where every source is
 * ready at version 1 and updated the same day shows none of them.
 */
function optionalColumns(rows: readonly LibraryRow[]): Column<LibraryRow>[] {
  const columns: Column<LibraryRow>[] = [];
  if (!uniform(rows, (r) => statusOf(r).label)) {
    columns.push({
      key: "status",
      header: "Status",
      width: "9rem",
      cell: (row) => {
        const label = statusOf(row);
        return label.label === "Ready" ? <span className="text-muted">Ready</span> : <StatusIndicator tone={label.tone} label={label.label} />;
      },
    });
  }
  if (rows.some((r) => (r.version ?? 1) > 1 || !r.isCurrent)) {
    columns.push({
      key: "version",
      header: "Version",
      width: "11rem",
      // Only revised or superseded sources say anything here; a first, current version is left blank.
      cell: (row) =>
        (row.version ?? 1) > 1 || !row.isCurrent ? (
          <span className="whitespace-nowrap tabular-nums text-secondary">{versionLabel(row)}</span>
        ) : null,
    });
  }
  if (!uniform(rows, (r) => (r.updatedAt ? formatDate(r.updatedAt) : "-"))) {
    columns.push({
      key: "updated",
      header: "Updated",
      width: "8rem",
      cell: (row) => <span className="whitespace-nowrap text-secondary">{row.updatedAt ? formatDate(row.updatedAt) : "-"}</span>,
    });
  }
  return columns;
}

/** Sources at their current version (plus superseded versions when asked), with columns that carry information. */
export function LibraryTable({
  ws,
  rows,
  filters,
  onClearFilters,
  empty,
}: {
  ws: string;
  rows: readonly LibraryRow[];
  filters: LibraryFilters;
  onClearFilters: () => void;
  empty: boolean;
}) {
  if (empty) {
    return (
      <EmptyState
        title="The library is empty"
        description="Sources appear here once they have been added to this workspace and processed."
      />
    );
  }
  const shown = filterLibraryRows(rows, filters);
  if (shown.length === 0) {
    return (
      <EmptyState
        title="No sources match these filters"
        action={
          <Button variant="secondary" onClick={onClearFilters}>
            Clear filters
          </Button>
        }
      />
    );
  }

  const columns: Column<LibraryRow>[] = [
    {
      key: "title",
      header: "Title",
      cell: (row) => {
        const muted = !row.isCurrent;
        if (row.bucket === "processing") {
          return <span className="font-medium text-secondary">{row.title}</span>;
        }
        return (
          <Link
            href={sourceHref(ws, row.sourceId)}
            className={`rounded-sm font-medium hover:underline ${muted ? "text-secondary" : "text-primary"}`}
          >
            {row.title}
          </Link>
        );
      },
    },
    { key: "class", header: "Category", width: "11rem", cell: (row) => <span className="whitespace-nowrap">{row.sourceClass ? sourceClass(row.sourceClass).label : "-"}</span> },
    { key: "type", header: "Type", width: "11rem", cell: (row) => <span className="whitespace-nowrap">{sourceType(row.sourceType).label}</span> },
    {
      key: "passages",
      header: "Passages",
      align: "right",
      width: "6.5rem",
      cell: (row) => <span className="tabular-nums text-secondary">{row.passages != null ? formatNumber(row.passages) : "-"}</span>,
    },
    ...optionalColumns(shown),
  ];

  return <Table caption="Sources in the Evidence Library" columns={columns} rows={shown} rowKey={(row) => row.key} />;
}
