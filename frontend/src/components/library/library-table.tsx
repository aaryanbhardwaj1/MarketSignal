"use client";

import Link from "next/link";
import { formatDate } from "@/lib/format";
import { sourceClass, sourceType } from "@/lib/labels";
import { filterLibraryRows, versionLabel, type LibraryFilters, type LibraryRow } from "@/lib/library-filters";
import { libraryStatusLabel, versionStatusLabel } from "@/lib/status";
import { Button } from "../ui/button";
import { EmptyState } from "../ui/states";
import { StatusIndicator } from "../ui/status-indicator";
import { Table, type Column } from "../ui/table";

export function sourceHref(ws: string, sourceId: string): string {
  return `/w/${encodeURIComponent(ws)}/evidence/sources/${encodeURIComponent(sourceId)}`;
}

/** Sources at their current version (plus superseded versions when asked); six business columns. */
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
    { key: "class", header: "Category", width: "9.5rem", cell: (row) => (row.sourceClass ? sourceClass(row.sourceClass).label : "-") },
    { key: "type", header: "Type", width: "8.5rem", cell: (row) => sourceType(row.sourceType).label },
    {
      key: "status",
      header: "Status",
      width: "8.5rem",
      cell: (row) => {
        const label = row.isCurrent ? versionStatusLabel(row.status) : libraryStatusLabel(row.bucket);
        return <StatusIndicator tone={label.tone} label={label.label} />;
      },
    },
    { key: "version", header: "Version", width: "8rem", cell: (row) => <span className="whitespace-nowrap tabular-nums text-secondary">{versionLabel(row)}</span> },
    { key: "updated", header: "Updated", width: "7.5rem", cell: (row) => <span className="whitespace-nowrap text-secondary">{row.updatedAt ? formatDate(row.updatedAt) : "-"}</span> },
  ];

  return <Table caption="Sources in the Evidence Library" columns={columns} rows={shown} rowKey={(row) => row.key} />;
}
