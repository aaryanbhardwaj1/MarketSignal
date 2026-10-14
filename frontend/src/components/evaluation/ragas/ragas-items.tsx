"use client";

import { useState } from "react";
import { Drawer } from "@/components/ui/drawer";
import { Select } from "@/components/ui/form-controls";
import { KeyValueList } from "@/components/ui/key-value";
import { ErrorState, LoadingRegion } from "@/components/ui/states";
import { Table, type Column } from "@/components/ui/table";
import type { RagasItem, RagasMetricDefinition, RagasRun, RagasRunId } from "@/lib/api/contracts";
import { useRagasItems } from "@/lib/api/hooks/evaluation";
import { cx } from "@/lib/cx";
import { formatEvalValue } from "@/lib/eval-view";
import { humanize } from "@/lib/format";
import { RAGAS_LOW_SCORE, configurationLabel, isLowScore, shortMetricLabel, sortByMetricAscending } from "@/lib/views/ragas";

/** The items endpoint returns at most this many per request. */
const PAGE_LIMIT = 50;
const LOW_LABEL = `Below ${RAGAS_LOW_SCORE}`;

export function ScoreValue({ value, strong = false }: { value: number | null | undefined; strong?: boolean }) {
  if (value == null) return <span className="text-muted">Not scorable</span>;
  const low = isLowScore(value);
  return (
    <span
      title={low ? LOW_LABEL : undefined}
      data-low={low ? "true" : undefined}
      className={cx(
        "tabular-nums",
        strong && "font-medium",
        low ? "rounded-sm bg-danger-subtle px-1 text-danger" : "text-primary",
      )}
    >
      {formatEvalValue(value, "ratio")}
    </span>
  );
}

/** Drawer body for one item: question, category, configuration and every stored score. */
export function RagasItemDetail({ item, defs }: { item: RagasItem; defs: RagasMetricDefinition[] }) {
  return (
    <div className="flex flex-col gap-5">
      <p className="text-md font-medium text-primary">{item.question}</p>
      <KeyValueList
        columns={2}
        items={[
          { label: "Category", value: configurationLabel(humanize(item.category)) },
          { label: "Configuration", value: configurationLabel(item.configuration) },
        ]}
      />
      <div>
        <p className="mb-2 text-sm font-semibold text-primary">Scores</p>
        <ul className="divide-y divide-border rounded-lg border border-border">
          {defs.map((d) => {
            const v = item.scores[d.key];
            return (
              <li key={d.key} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                <span className="text-secondary">{d.label}</span>
                <span className="flex items-center gap-2">
                  {isLowScore(v) && <span className="text-xs text-danger">{LOW_LABEL}</span>}
                  <ScoreValue value={v} />
                </span>
              </li>
            );
          })}
        </ul>
        <p className="mt-2 text-xs text-muted">
          Not scorable means the metric has no value for this item, for example when the answer cites nothing. Model-judged
          metrics were not run for any item.
        </p>
      </div>
    </div>
  );
}

function useAllItems(runId: RagasRunId) {
  const first = useRagasItems(runId, { offset: 0, limit: PAGE_LIMIT });
  const total = first.data?.total ?? 0;
  const second = useRagasItems(total > PAGE_LIMIT ? runId : null, { offset: PAGE_LIMIT, limit: PAGE_LIMIT });
  const items = [...(first.data?.items ?? []), ...(total > PAGE_LIMIT ? (second.data?.items ?? []) : [])];
  const pending = first.isPending || (total > PAGE_LIMIT && second.isPending);
  const failed = first.isError ? first : second.isError ? second : null;
  return { items, total, pending, failed };
}

function ItemsTable({ run, defs }: { run: RagasRun; defs: RagasMetricDefinition[] }) {
  const [configuration, setConfiguration] = useState("");
  const [sortKey, setSortKey] = useState(defs[0]?.key ?? "");
  const [open, setOpen] = useState<RagasItem | null>(null);
  const { items, total, pending, failed } = useAllItems(run.id);
  const multi = run.configurations.length > 1;

  const filtered = configuration ? items.filter((i) => i.configuration === configuration) : items;
  const rows = sortByMetricAscending(filtered, sortKey);
  const columns: Column<RagasItem>[] = [
    {
      key: "question",
      header: "Question",
      cell: (i) => (
        <span className="flex min-w-56 flex-col gap-0.5">
          <span className="line-clamp-2 text-sm text-primary">{i.question}</span>
          <span className="font-mono text-xs text-muted">{i.item_id}</span>
        </span>
      ),
    },
    { key: "category", header: "Category", cell: (i) => <span className="text-sm text-secondary">{configurationLabel(humanize(i.category))}</span> },
    ...(multi
      ? [{ key: "configuration", header: "Configuration", cell: (i: RagasItem) => configurationLabel(i.configuration) }]
      : []),
    ...defs.map(
      (d): Column<RagasItem> => ({
        key: d.key,
        // Two short lines ("Recall" / "IDs, pack") keep six metric columns inside the page width.
        header: (
          <span className={cx("inline-flex flex-col items-end", d.key === sortKey && "text-primary")}>
            {shortMetricLabel(d)
              .split(" · ")
              .map((part) => (
                <span key={part} className="whitespace-nowrap">
                  {part}
                </span>
              ))}
          </span>
        ),
        align: "right",
        cell: (i) => <ScoreValue value={i.scores[d.key]} strong={d.key === sortKey} />,
      }),
    ),
  ];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-4">
        {multi && (
          <label className="flex flex-col gap-1 text-sm text-muted">
            Configuration
            <Select
              controlSize="sm"
              value={configuration}
              onChange={(e) => setConfiguration(e.target.value)}
              options={[
                { value: "", label: "All configurations" },
                ...run.configurations.map((c) => ({ value: c.name, label: configurationLabel(c.name) })),
              ]}
              className="min-w-48"
            />
          </label>
        )}
        <label className="flex flex-col gap-1 text-sm text-muted">
          Lowest scores first by
          <Select
            controlSize="sm"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value)}
            options={defs.map((d) => ({ value: d.key, label: d.label }))}
            className="min-w-64"
          />
        </label>
        <p className="pb-1.5 text-xs text-muted">
          Scores {LOW_LABEL.toLowerCase()} are highlighted; items that are not scorable sort last.
        </p>
      </div>
      {pending ? (
        <LoadingRegion label="Loading item scores" lines={6} />
      ) : failed ? (
        <ErrorState
          title="Item scores could not be loaded"
          description="The run summary above is unaffected."
          error={failed.error}
          retry={() => void failed.refetch()}
          devDetail={failed.error instanceof Error ? failed.error.message : undefined}
        />
      ) : (
        <>
          <Table
            columns={columns}
            rows={rows}
            rowKey={(i) => `${i.configuration}:${i.item_id}`}
            caption={`Item-level RAGAS scores, ${run.title}`}
            onRowClick={setOpen}
            density="compact"
            stickyHeader
            maxHeight="32rem"
            empty="No scored items for this selection."
          />
          {total > PAGE_LIMIT * 2 && (
            <p className="text-xs text-muted">Showing the first {PAGE_LIMIT * 2} items of this run.</p>
          )}
        </>
      )}
      <Drawer
        open={open !== null}
        onClose={() => setOpen(null)}
        title="Item scores"
        subtitle={open ? <span className="font-mono">{open.item_id}</span> : undefined}
      >
        {open && <RagasItemDetail item={open} defs={defs} />}
      </Drawer>
    </div>
  );
}

export function RagasItems({ runs, defs }: { runs: RagasRun[]; defs: RagasMetricDefinition[] }) {
  const [runId, setRunId] = useState<RagasRunId | null>(runs[0]?.id ?? null);
  const run = runs.find((r) => r.id === runId) ?? runs[0];
  if (!run) return null;
  return (
    <div className="flex flex-col gap-3">
      {runs.length > 1 && (
        <label className="flex flex-col gap-1 text-sm text-muted">
          Run
          <Select
            controlSize="sm"
            value={run.id}
            onChange={(e) => setRunId(e.target.value as RagasRunId)}
            options={runs.map((r) => ({ value: r.id, label: r.title }))}
            className="max-w-md"
          />
        </label>
      )}
      <ItemsTable key={run.id} run={run} defs={defs} />
    </div>
  );
}
