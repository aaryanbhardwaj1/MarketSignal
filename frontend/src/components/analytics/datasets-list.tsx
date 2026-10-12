"use client";

import { useId, useState } from "react";
import type { DatasetColumn, DatasetInfo } from "@/lib/api/contracts";
import { useDataset } from "@/lib/api/hooks/core";
import { formatNumber, humanizeColumn, tableLabel } from "@/lib/format";
import { sourceClass } from "@/lib/labels";
import { Card } from "../ui/card";
import { ErrorState, LoadingRegion } from "../ui/states";
import { Table, type Column } from "../ui/table";
import { columnUnitLabel } from "./analysis-format";

const TYPE_LABELS: Record<string, string> = {
  categorical: "Category",
  numeric: "Number",
  date: "Date",
  text: "Text",
  boolean: "Yes / no",
};

function DatasetColumns({ ws, dataset }: { ws: string; dataset: string }) {
  const query = useDataset(ws, dataset);
  if (query.isPending) return <LoadingRegion label="Loading columns" lines={4} />;
  if (query.isError) return <ErrorState title="Columns could not be loaded" description="Try again in a moment." error={query.error} retry={() => void query.refetch()} />;
  const columns: Column<DatasetColumn>[] = [
    { key: "name", header: "Column", cell: (c) => humanizeColumn(c.name) },
    { key: "type", header: "Type", cell: (c) => TYPE_LABELS[c.type] ?? humanizeColumn(c.type) },
    { key: "unit", header: "Unit", cell: (c) => columnUnitLabel(c.unit) },
    {
      key: "levels",
      header: "Values",
      cell: (c) =>
        c.levels.length > 0 ? (
          <span className="text-secondary">
            {c.levels.slice(0, 4).join(", ")}
            {c.levels.length > 4 && ` and ${formatNumber(c.levels.length - 4)} more`}
          </span>
        ) : (
          <span className="text-muted">-</span>
        ),
    },
    { key: "filled", header: "Filled rows", align: "right", cell: (c) => formatNumber(c.non_empty) },
  ];
  return <Table caption={`Columns in ${query.data.title}`} columns={columns} rows={query.data.columns} rowKey={(c) => c.name} density="compact" />;
}

function DatasetItem({ ws, info }: { ws: string; info: DatasetInfo }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <li className="border-b border-border last:border-b-0">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="grid w-full grid-cols-[1rem_minmax(0,1fr)_10rem_6rem_7rem] items-center gap-3 px-4 py-2.5 text-left hover:bg-surface-muted/60"
      >
        <svg aria-hidden viewBox="0 0 16 16" className={`h-3.5 w-3.5 text-muted transition-transform ${open ? "rotate-90" : ""}`} fill="none" stroke="currentColor" strokeWidth="1.75">
          <path d="m6 4 4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="min-w-0">
          <span className="block truncate text-base font-medium text-primary">{info.title}</span>
          <span className="block truncate text-sm text-muted">Table: {tableLabel(info.table)}</span>
        </span>
        <span className="text-sm text-secondary">{sourceClass(info.source_class).label}</span>
        <span className="text-sm text-secondary">Version {info.source_version}</span>
        <span className="text-right text-sm tabular-nums text-secondary">{formatNumber(info.row_count)} rows</span>
      </button>
      {open && (
        <div id={panelId} className="border-t border-border bg-surface-muted/40 px-4 py-3">
          <DatasetColumns ws={ws} dataset={info.dataset} />
        </div>
      )}
    </li>
  );
}

/** Structured datasets available for computed figures; expand a row to see its columns. */
export function DatasetsList({ ws, datasets, truncated }: { ws: string; datasets: readonly DatasetInfo[]; truncated: boolean }) {
  return (
    <div className="flex flex-col gap-2">
      <Card padding="none" className="overflow-hidden">
        <div className="grid grid-cols-[1rem_minmax(0,1fr)_10rem_6rem_7rem] gap-3 border-b border-border bg-surface-muted px-4 py-2.5 text-sm font-medium text-secondary">
          <span />
          <span>Dataset</span>
          <span>Category</span>
          <span>Version</span>
          <span className="text-right">Rows</span>
        </div>
        <ul aria-label="Datasets">
          {datasets.map((d) => (
            <DatasetItem key={d.dataset} ws={ws} info={d} />
          ))}
        </ul>
      </Card>
      {truncated && <p className="text-sm text-muted">Showing the first datasets only.</p>}
    </div>
  );
}
