"use client";

import Link from "next/link";
import { useState } from "react";
import { HBarChart } from "@/components/charts";
import { Callout } from "@/components/ui/callout";
import { Select } from "@/components/ui/form-controls";
import { Section } from "@/components/ui/section";
import { Table, type Column } from "@/components/ui/table";
import type { EvalCatalog } from "@/lib/api/contracts";
import { evalRunHref } from "@/lib/eval-view";
import { formatNumber, humanize } from "@/lib/format";

type FailureRun = EvalCatalog["failure_runs"][number];

const linkClass = "rounded-sm text-accent-text hover:underline";

const BUCKET_LABELS: Record<string, string> = {
  both_miss: "Missed by both lanes",
  dense_only: "Found only by vector search",
  hybrid_only: "Found only by hybrid",
  mixed: "Mixed retrieval outcome",
  verifier_false_positive: "Verifier rejected a supported claim",
  research_behaviour_fail: "Research behaviour failure",
  values_mismatch: "Stated values don't match gold",
  task_type_wrong: "Routed to the wrong task type",
};

/** Plain label for a stored failure bucket id; unknown ids are humanised. */
export function failureBucketLabel(id: string): string {
  const known = BUCKET_LABELS[id];
  if (known) return known;
  const text = humanize(id);
  return text.charAt(0).toUpperCase() + text.slice(1);
}

interface BucketRow {
  key: string;
  run: FailureRun;
  bucket: FailureRun["buckets"][number] | null;
}

function bucketRows(runs: readonly FailureRun[]): BucketRow[] {
  return runs.flatMap((run): BucketRow[] =>
    run.buckets.length === 0
      ? [{ key: `${run.run_id}:none`, run, bucket: null }]
      : run.buckets.map((bucket) => ({ key: `${run.run_id}:${bucket.id}`, run, bucket })),
  );
}

function RunChart({ runs }: { runs: readonly FailureRun[] }) {
  const withBuckets = runs.filter((r) => r.buckets.length > 0);
  const [runId, setRunId] = useState<string>(withBuckets[0]?.run_id ?? "");
  const run = withBuckets.find((r) => r.run_id === runId) ?? withBuckets[0];
  if (!run) return <p className="text-sm text-muted">No failures recorded in any run.</p>;
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <label className="flex flex-wrap items-center gap-2 text-sm text-muted">
        Evaluation run
        <Select
          controlSize="sm"
          value={run.run_id}
          onChange={(e) => setRunId(e.target.value)}
          options={withBuckets.map((r) => ({ value: r.run_id, label: r.label }))}
          className="min-w-72"
        />
      </label>
      <HBarChart
        className="mt-3"
        data={run.buckets.map((b) => ({ label: failureBucketLabel(b.id), value: b.n }))}
        domain={[0, run.item_count]}
        format={(v) => formatNumber(v)}
        valueLabel="Items"
        labelWidth="16rem"
        ariaLabel={`Items per failure bucket, ${run.label}`}
        caption={`Items per failure bucket, on a scale of all ${formatNumber(run.item_count)} items in ${run.label}.`}
      />
    </div>
  );
}

export function FailuresTab({ catalog, ws }: { catalog: EvalCatalog; ws: string }) {
  const columns: Column<BucketRow>[] = [
    {
      key: "run",
      header: "Evaluation run",
      cell: (r) => (
        <Link href={evalRunHref(ws, r.run.run_id)} className={`${linkClass} font-medium`}>
          {r.run.label}
        </Link>
      ),
    },
    {
      key: "bucket",
      header: "Failure bucket",
      cell: (r) =>
        r.bucket ? (
          <Link href={evalRunHref(ws, r.run.run_id, { bucket: r.bucket.id })} className={linkClass} title={r.bucket.label}>
            {failureBucketLabel(r.bucket.id)}
          </Link>
        ) : (
          <span className="text-muted">No failures recorded in this run</span>
        ),
    },
    {
      key: "items",
      header: "Items",
      align: "right",
      cell: (r) => (
        <span className="tabular-nums">
          {r.bucket ? `${formatNumber(r.bucket.n)} of ${formatNumber(r.run.item_count)}` : `0 of ${formatNumber(r.run.item_count)}`}
        </span>
      ),
    },
  ];
  return (
    <div>
      <Callout tone="info" title="Failed cases are preserved, not discarded.">
        Every item from each run is kept, including misses and incorrect answers. Buckets come from the labels stored with
        each run; no new root-cause taxonomy is inferred here. Counts are per run and are not added up across runs.
      </Callout>
      <Section title="Failure buckets by run" description="Choose a run to see how its failures split across buckets.">
        <RunChart runs={catalog.failure_runs} />
      </Section>
      <Section title="Runs and failure buckets" description="Choose a run or a bucket to review its items, expected evidence and stored checks.">
        <Table columns={columns} rows={bucketRows(catalog.failure_runs)} rowKey={(r) => r.key} caption="Failure buckets per evaluation run" />
      </Section>
    </div>
  );
}
