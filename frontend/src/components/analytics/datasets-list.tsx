"use client";

import { useState } from "react";
import type { DatasetColumn, DatasetInfo } from "@/lib/api/contracts";
import { useDataset } from "@/lib/api/hooks/core";
import { formatNumber, humanizeColumn, tableLabel } from "@/lib/format";
import { Disclosure } from "../ui/disclosure";
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
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm tabular-nums text-muted">{`${formatNumber(query.data.columns.length)} columns`}</p>
      <Table caption={`Columns in ${query.data.title}`} columns={columns} rows={query.data.columns} rowKey={(c) => c.name} density="compact" />
    </div>
  );
}

function DatasetItem({ ws, info }: { ws: string; info: DatasetInfo }) {
  // Columns load on first open only; Disclosure keeps closed content mounted.
  const [seen, setSeen] = useState(false);
  const table = tableLabel(info.table);
  const summary = (
    <span className="flex min-w-0 flex-1 flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
      <span className="min-w-0">
        <span className="text-base font-medium text-primary">{info.title}</span>
        {table.toLowerCase() !== info.title.toLowerCase() && <span className="ml-2 text-sm font-normal text-muted">{table}</span>}
      </span>
      <span className="flex gap-4 text-sm font-normal tabular-nums text-secondary">
        <span>{`${formatNumber(info.row_count)} rows`}</span>
        <span>{`Version ${info.source_version}`}</span>
      </span>
    </span>
  );
  return (
    <li onClickCapture={() => setSeen(true)}>
      <Disclosure summary={summary}>{seen ? <DatasetColumns ws={ws} dataset={info.dataset} /> : null}</Disclosure>
    </li>
  );
}

/** Structured datasets available for computed figures; expand one to see its columns. */
export function DatasetsList({ ws, datasets, truncated }: { ws: string; datasets: readonly DatasetInfo[]; truncated: boolean }) {
  return (
    <div className="flex flex-col gap-2">
      <ul aria-label="Datasets" className="flex flex-col gap-2">
        {datasets.map((d) => (
          <DatasetItem key={d.dataset} ws={ws} info={d} />
        ))}
      </ul>
      {truncated && <p className="text-sm text-muted">Showing the first datasets only.</p>}
    </div>
  );
}
