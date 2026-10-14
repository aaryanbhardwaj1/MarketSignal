"use client";

import { useState } from "react";
import { GroupedBarChart } from "@/components/charts";
import { NotRun } from "@/components/ui/not-run";
import { Section } from "@/components/ui/section";
import { Table, type Column } from "@/components/ui/table";
import type { EvalCatalog } from "@/lib/api/contracts";
import { SPLIT_LABEL, caveatsFor, formatEvalValue, isResourceRow, parseSplitParam, type EvalSplit } from "@/lib/eval-view";
import { formatNumber } from "@/lib/format";
import { Caveats, ProvenanceTable } from "./caveats";
import { Segmented } from "@/components/ui/segmented";
import { EVIDENCE_ROWS, researchTakeaway } from "./dashboard/derive";
import { DeltaCell, MetricCell, SourceRef } from "./metric-bits";

type Tradeoff = EvalCatalog["research_tradeoff"][number];
type Row = Tradeoff["rows"][number];

const splitName = (s: Tradeoff["split"]) => SPLIT_LABEL[s];
const ratio3 = (v: number) => formatEvalValue(v, "ratio");

/** Two thin bars on the row's own scale, standard above research in the chart's series colours (decorative: values sit in the adjacent cells). */
function PairBars({ row }: { row: Row }) {
  const s = row.standard.value ?? 0;
  const r = row.research.value ?? 0;
  const max = Math.max(s, r);
  if (max <= 0) return null;
  const bar = (v: number, cls: string) => (
    <span className="block h-1.5 rounded-sm bg-chart-track">
      <span className={`block h-1.5 rounded-sm ${cls}`} style={{ width: `${(v / max) * 100}%` }} />
    </span>
  );
  return (
    <span aria-hidden className="flex w-28 flex-col gap-1">
      {bar(s, "bg-chart-1")}
      {bar(r, "bg-chart-2")}
    </span>
  );
}

function PairedTable({ group, rows, caption }: { group: Tradeoff; rows: Row[]; caption: string }) {
  const columns: Column<Row>[] = [
    { key: "label", header: "Measure", width: "28%", cell: (r) => <span className="font-medium">{r.label}</span> },
    { key: "std", header: "Standard", align: "right", width: "16%", cell: (r) => <MetricCell metric={r.standard} /> },
    { key: "res", header: "Research", align: "right", width: "16%", cell: (r) => <MetricCell metric={r.research} /> },
    { key: "bars", header: <span className="sr-only">Visual comparison</span>, width: "10%", cell: (r) => <PairBars row={r} /> },
    {
      key: "delta",
      header: "Difference (research − standard)",
      align: "right",
      width: "30%",
      cell: (r) => (
        <DeltaCell metric={r.delta} direction={isResourceRow(r.id) ? "lower" : "higher"} resource={isResourceRow(r.id)} />
      ),
    },
  ];
  return (
    <Table
      columns={columns}
      rows={rows}
      rowKey={(r) => r.id}
      showCaption
      caption={`${caption} ${splitName(group.split)} split, ${formatNumber(group.n_pairs)} paired questions.`}
    />
  );
}

function EvidenceChart({ group }: { group: Tradeoff }) {
  const rows = EVIDENCE_ROWS.map((id) => group.rows.find((r) => r.id === id)).filter((r): r is Row => !!r);
  if (rows.length === 0) return null;
  return (
    <GroupedBarChart
      ariaLabel={`Evidence measures, standard versus research, ${splitName(group.split)} split`}
      categories={rows.map((r) => r.label)}
      series={[
        { name: "Standard", values: rows.map((r) => r.standard.value ?? 0) },
        { name: "Research", values: rows.map((r) => r.research.value ?? 0) },
      ]}
      format={ratio3}
      caption={
        <span className="flex flex-wrap items-center gap-2">
          Item means on the same paired questions; differences and intervals are in the table.
          <SourceRef path={group.provenance.path} />
        </span>
      }
    />
  );
}

export function ResearchTab({
  catalog,
  split: splitProp,
  onSplitChange,
}: {
  catalog: EvalCatalog;
  split?: string | null;
  onSplitChange?: (split: EvalSplit) => void;
}) {
  const groups = catalog.research_tradeoff;
  const [localSplit, setLocalSplit] = useState<EvalSplit | null>(null);
  const split = parseSplitParam(onSplitChange ? splitProp : (localSplit ?? splitProp), groups.map((g) => g.split));
  const changeSplit = onSplitChange ?? setLocalSplit;
  const group = groups.find((g) => g.split === split) ?? groups[0];

  return (
    <div>
      {group ? (
        <>
          <section aria-label="Takeaway" className="rounded-lg border border-border bg-surface px-4 py-3 shadow-raised">
            <p className="text-md font-semibold text-primary">{researchTakeaway(group)}</p>
            <p className="mt-1 max-w-reading text-sm text-secondary">
              It is not better on every measure: a difference whose interval crosses zero is not distinguishable, and
              research mode uses more model calls, tool calls, tokens and time per question.
            </p>
          </section>

          <Section
            title="Evidence and answer quality"
            description="Same questions answered in both modes; differences are paired, with 95% confidence intervals."
            actions={
              <Segmented
                label="Split"
                value={group.split}
                options={groups.map((g) => ({ value: g.split, label: splitName(g.split) }))}
                onChange={changeSplit}
              />
            }
          >
            <div className="max-w-3xl">
              <EvidenceChart group={group} />
            </div>
            <div className="mt-6">
              <PairedTable group={group} rows={group.rows.filter((r) => !isResourceRow(r.id))} caption="Quality measures." />
            </div>
          </Section>

          <Section
            title="Cost and speed"
            description="Calls, tokens and cost per run as recorded by the eval harness; latency percentiles have no paired interval."
          >
            <PairedTable group={group} rows={group.rows.filter((r) => isResourceRow(r.id))} caption="Resource measures." />
          </Section>

          <Section title="Run provenance">
            <ProvenanceTable
              rows={groups.map((g) => ({ id: g.split, label: `Standard vs research (${splitName(g.split).toLowerCase()})`, provenance: g.provenance }))}
              caption="Standard vs research run provenance"
            />
          </Section>
        </>
      ) : (
        <NotRun reason="No standard-versus-research comparison is recorded in the evaluation catalog." />
      )}

      <div className="mt-8">
        <Caveats caveats={caveatsFor(catalog, "research_tradeoff")} title="Caveats for this comparison" />
      </div>
    </div>
  );
}
