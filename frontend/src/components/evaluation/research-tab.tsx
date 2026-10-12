"use client";

import { useState } from "react";
import { Callout } from "@/components/ui/callout";
import { Section } from "@/components/ui/section";
import { Table, type Column } from "@/components/ui/table";
import type { EvalCatalog } from "@/lib/api/contracts";
import { caveatsFor, isResourceRow } from "@/lib/eval-view";
import { formatNumber } from "@/lib/format";
import { Caveats, ProvenanceTable } from "./caveats";
import { DeltaCell, MetricCell, Segmented } from "./metric-bits";

type Tradeoff = EvalCatalog["research_tradeoff"][number];
type Row = Tradeoff["rows"][number];

const splitName = (s: Tradeoff["split"]) => (s === "test" ? "Held-out test" : "Dev");

function PairedTable({ group, rows, caption }: { group: Tradeoff; rows: Row[]; caption: string }) {
  const columns: Column<Row>[] = [
    { key: "label", header: "Measure", width: "34%", cell: (r) => <span className="font-medium">{r.label}</span> },
    { key: "std", header: "Standard", align: "right", width: "18%", cell: (r) => <MetricCell metric={r.standard} /> },
    { key: "res", header: "Research", align: "right", width: "18%", cell: (r) => <MetricCell metric={r.research} /> },
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

export function ResearchTab({ catalog }: { catalog: EvalCatalog }) {
  const groups = catalog.research_tradeoff;
  const [split, setSplit] = useState<Tradeoff["split"]>(groups.some((g) => g.split === "test") ? "test" : "dev");
  const group = groups.find((g) => g.split === split) ?? groups[0];

  return (
    <div>
      <Callout tone="info" title="Research mode finds more relevant evidence, but costs more and takes longer.">
        It is not better on every measure: some quality differences are not distinguishable from standard mode, and it
        uses more model calls, tokens and time per question. Choose it when completeness matters more than speed and cost.
      </Callout>

      {group && (
        <>
          <Section
            title="Answer quality"
            description="Same questions answered in both modes; differences are paired, with 95% confidence intervals."
            actions={
              <Segmented
                label="Split"
                value={group.split}
                options={groups.map((g) => ({ value: g.split, label: splitName(g.split) }))}
                onChange={setSplit}
              />
            }
          >
            <PairedTable group={group} rows={group.rows.filter((r) => !isResourceRow(r.id))} caption="Quality measures." />
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
      )}

      <div className="mt-8">
        <Caveats caveats={caveatsFor(catalog, "research_tradeoff")} title="Caveats for this comparison" />
      </div>
    </div>
  );
}
