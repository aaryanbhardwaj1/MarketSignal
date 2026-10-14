"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { HBarChart } from "@/components/charts";
import { Section } from "@/components/ui/section";
import { Table, type Column } from "@/components/ui/table";
import type { EvalCatalog, EvalMetric, EvalRunId } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import {
  glossaryTitle,
  type GlossaryKey,
  DECISION_OUTCOME,
  SPLIT_LABEL,
  caveatsFor,
  ciOf,
  parseSplitParam,
  type EvalSplit,
  deltaVerdict,
  formatCi,
  formatEvalValue,
  formatSigned,
  sourceLocator,
} from "@/lib/eval-view";
import { formatMs, formatNumber } from "@/lib/format";
import { Caveats } from "./caveats";
import { MetricGlossary } from "./metric-glossary";
import { Segmented } from "@/components/ui/segmented";
import { DeltaCell, MetricCell, MetricSource, SourceRef } from "./metric-bits";

type RetrievalRun = EvalCatalog["retrieval"]["runs"][number];
type Arm = RetrievalRun["arms"][number];
type Comparison = EvalCatalog["retrieval"]["comparisons"][number];
type Decision = EvalCatalog["retrieval"]["decisions"][number];
type Population = "eligible" | "all";

const ARM_METRICS = [
  { key: "hit@1", header: "Hit@1", gloss: "hit" },
  { key: "hit@10", header: "Hit@10", gloss: "hit" },
  { key: "recall@10", header: "Recall@10", gloss: "recall" },
  { key: "mrr", header: "MRR", gloss: "mrr" },
] as const;

const ARM_CHARTS = [
  { key: "hit@1", header: "Hit@1", gloss: "hit" },
  { key: "hit@10", header: "Hit@10", gloss: "hit" },
  { key: "recall@10", header: "Recall@10", gloss: "recall" },
  { key: "mrr", header: "MRR", gloss: "mrr" },
] as const;

/** Column header with its glossary definition on hover. */
const abbr = (text: string, key: GlossaryKey) => <span title={glossaryTitle(key)}>{text}</span>;


function armLabel(run: RetrievalRun | undefined, arm: string): string {
  return run?.arms.find((a) => a.arm === arm)?.label ?? arm;
}

function findComparison(c: EvalCatalog, runId: EvalRunId, a: string, b: string): Comparison | undefined {
  return c.retrieval.comparisons.find((x) => x.run_id === runId && x.a === a && x.b === b);
}

const metricOf = (cmp: Comparison | undefined, suffix: string): EvalMetric | undefined =>
  cmp?.metrics.find((m) => m.id.endsWith(`.${suffix}`));

/** The production choice and why: the adopted default, its held-out evidence, and what the reranker did. */
function ProductionChoice({ catalog, testRun }: { catalog: EvalCatalog; testRun: RetrievalRun | undefined }) {
  const adopted = catalog.retrieval.decisions.find((d) => d.id === "hybrid-default");
  const hybridArm = testRun?.arms.find((a) => a.is_default);
  const dense = testRun && findComparison(catalog, testRun.run_id, "dense", hybridArm?.arm ?? "hybrid");
  const d1 = metricOf(dense, "d_recall@10");
  const v1 = d1 ? deltaVerdict(d1) : null;
  if (!adopted && !d1) return null;
  return (
    <section
      aria-label="Production choice"
      className="rounded-lg border border-accent/30 bg-accent-subtle px-4 py-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="accent" size="md">
          Production choice
        </Badge>
        <p className="text-base font-semibold text-primary">{adopted?.title ?? hybridArm?.label}</p>
      </div>
      {adopted && <p className="mt-1.5 max-w-reading text-sm text-secondary">{adopted.text}</p>}
      {d1 && v1 && dense && (
        <p className="mt-2 flex flex-wrap items-baseline gap-x-2 text-sm text-secondary">
          <span>{d1.label}:</span>
          <span className="font-semibold tabular-nums text-primary">{formatSigned(d1.value, d1.unit)}</span>
          <span className="tabular-nums">
            {formatCi(d1, { signed: true })}, n = {formatNumber(dense.n)}
          </span>
          <Badge tone={v1.tone}>{v1.label}</Badge>
          <MetricSource source={d1.source} />
        </p>
      )}
    </section>
  );
}

const ratio3 = (v: number) => formatEvalValue(v, "ratio");

/** Small multiples: one bar chart per measure, CI whiskers from the catalog, production arm emphasised. */
function ArmCharts({ run, population }: { run: RetrievalRun; population: Population }) {
  return (
    <div className="grid gap-x-8 gap-y-6 lg:grid-cols-2">
      {ARM_CHARTS.map((m) => (
        <HBarChart
          key={m.key}
          title={abbr(m.header, m.gloss)}
          ariaLabel={`${m.header} by retrieval method, ${run.label}`}
          domain={[0, 1]}
          format={ratio3}
          valueLabel={m.header}
          labelWidth="13rem"
          data={run.arms.map((a) => {
            const metric = a[population][m.key];
            const ci = metric ? ciOf(metric) : null;
            return {
              label: a.label,
              value: metric?.value ?? 0,
              ...(ci ? { low: ci[0], high: ci[1] } : {}),
              emphasis: a.is_default,
            };
          })}
        />
      ))}
    </div>
  );
}

function LatencyChart({ run }: { run: RetrievalRun }) {
  return (
    <HBarChart
      title={abbr("Latency p50 per query", "p50")}
      ariaLabel={`Median retrieval latency by method, ${run.label}`}
      format={formatMs}
      valueLabel="Latency p50"
      labelWidth="13rem"
      data={run.arms.map((a) => ({ label: a.label, value: a.latency_ms.p50, emphasis: a.is_default }))}
      caption={
        <span className="flex flex-wrap items-center gap-2">
          Linear scale; read the value labels. p95 values are in the table below.
          <SourceRef path={run.provenance.path} note="Per-arm latency percentiles from this run's results file." />
        </span>
      }
    />
  );
}

function ArmsTable({ run, population }: { run: RetrievalRun; population: Population }) {
  const columns: Column<Arm>[] = [
    {
      key: "arm",
      header: "Retrieval method",
      cell: (a) => (
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{a.label}</span>
          {a.is_default && <Badge tone="success">Adopted default</Badge>}
        </span>
      ),
    },
    ...ARM_METRICS.map(
      (m): Column<Arm> => ({ key: m.key, header: abbr(m.header, m.gloss), align: "right", cell: (a) => <MetricCell metric={a[population][m.key]} /> }),
    ),
    {
      key: "latency",
      header: abbr("Latency p50 / p95", "p50"),
      align: "right",
      cell: (a) => (
        <span className="inline-flex flex-col items-end">
          <span className="whitespace-nowrap tabular-nums">
            {formatMs(a.latency_ms.p50)} / {formatMs(a.latency_ms.p95)}
          </span>
          <span className="mt-0.5 text-xs">
            <SourceRef path={run.provenance.path} note="Per-arm latency percentiles from this run's results file." />
          </span>
        </span>
      ),
    },
  ];
  const n = population === "eligible" ? run.n_eligible : run.n;
  return (
    <Table
      columns={columns}
      rows={run.arms}
      rowKey={(a) => a.arm}
      showCaption
      caption={`${run.label}: ${population === "eligible" ? "retrieval-eligible items" : "all items"}, n = ${formatNumber(n)}. 95% confidence intervals under each value.`}
    />
  );
}

function ComparisonsTable({ catalog, run }: { catalog: EvalCatalog; run: RetrievalRun }) {
  const rows = catalog.retrieval.comparisons.filter((c) => c.run_id === run.run_id);
  const columns: Column<Comparison>[] = [
    {
      key: "pair",
      header: "Comparison",
      cell: (c) => (
        <span className="font-medium">
          {armLabel(run, c.a)} <span aria-label="to">→</span> {armLabel(run, c.b)}
        </span>
      ),
    },
    { key: "recall", header: abbr("Δ Recall@10", "recall"), align: "right", cell: (c) => <DeltaCell metric={metricOf(c, "d_recall@10")} /> },
    { key: "mrr", header: abbr("Δ MRR", "mrr"), align: "right", cell: (c) => <DeltaCell metric={metricOf(c, "d_mrr")} /> },
    {
      key: "hits",
      header: abbr("Hit@10 items gained / lost", "hit"),
      align: "right",
      cell: (c) => (
        <span className="inline-flex flex-col items-end">
          <span className="tabular-nums">
            +{formatNumber(c.hit_at_10.gains)} / −{formatNumber(c.hit_at_10.losses)}
          </span>
          <span className="text-xs text-muted">
            {c.hit_at_10.p == null ? "No sign test" : `Sign test p = ${formatNumber(c.hit_at_10.p, 3)}`} · n = {formatNumber(c.n)}
          </span>
        </span>
      ),
    },
  ];
  return (
    <Table
      columns={columns}
      rows={rows}
      rowKey={(c) => `${c.a}-${c.b}`}
      showCaption
      caption={`${run.label}: paired differences on retrieval-eligible items. A confidence interval that includes zero is read as not distinguishable.`}
      empty="No paired comparisons recorded for this run."
    />
  );
}

function DecisionCard({ decision }: { decision: Decision }) {
  const outcome = DECISION_OUTCOME[decision.outcome];
  const negative = decision.outcome !== "adopted";
  return (
    <li
      className={cx(
        "relative overflow-hidden rounded-lg border border-border bg-surface p-4",
        negative && "before:absolute before:inset-y-0 before:left-0 before:w-0.5",
        decision.outcome === "rejected" ? "before:bg-danger" : "before:bg-warn",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="min-w-0 flex-1 text-base font-semibold text-primary">{decision.title}</p>
        <Badge tone={outcome.tone} size="md">
          {outcome.label}
        </Badge>
      </div>
      <p className="mt-1 text-base text-secondary">{decision.text}</p>
      {decision.metrics.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1.5 border-t border-border pt-3">
          {decision.metrics.map((m) => (
            <li key={m.id} className="flex flex-wrap items-baseline justify-between gap-x-4 text-sm">
              <span className="text-secondary">{m.label}</span>
              <span className="flex flex-wrap items-baseline gap-x-2 text-right">
                <span className="font-medium tabular-nums text-primary">
                  {m.label.startsWith("Δ") ? formatSigned(m.value, m.unit) : formatEvalValue(m.value, m.unit)}
                </span>
                <span className="text-xs tabular-nums text-muted">
                  {formatCi(m, { signed: m.label.startsWith("Δ") })}
                  {m.n != null ? ` · n = ${formatNumber(m.n)}` : ""}
                </span>
                <MetricSource source={m.source} />
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-muted">
        Reasoning recorded in{" "}
        <SourceRef path={decision.source.path} locator={sourceLocator(decision.source)} />
        <span className="ml-1 font-mono">{decision.source.path}</span>
      </p>
    </li>
  );
}

export function RetrievalTab({
  catalog,
  split: splitProp,
  onSplitChange,
}: {
  catalog: EvalCatalog;
  /** `?split=` value; the page keeps it in the URL. */
  split?: string | null;
  onSplitChange?: (split: EvalSplit) => void;
}) {
  const runs = catalog.retrieval.runs;
  const available = runs.map((r) => r.provenance.split ?? "");
  const [localSplit, setLocalSplit] = useState<EvalSplit | null>(null);
  const split = parseSplitParam(onSplitChange ? splitProp : (localSplit ?? splitProp), available);
  const changeSplit = onSplitChange ?? setLocalSplit;
  const [population, setPopulation] = useState<Population>("eligible");
  const testRun = runs.find((r) => r.provenance.split === "test");
  const run = runs.find((r) => r.provenance.split === split) ?? runs[0];
  const negative = catalog.retrieval.decisions.filter((d) => d.outcome !== "adopted");
  const adopted = catalog.retrieval.decisions.filter((d) => d.outcome === "adopted");

  return (
    <div>
      <ProductionChoice catalog={catalog} testRun={testRun} />
      <div className="mt-4">
        <MetricGlossary keys={["hit", "recall", "mrr", "eligible", "ci", "pp", "rrf", "bge", "p50"]} />
      </div>

      {run && (
        <Section
          title="Retrieval methods compared"
          description="Same questions, four methods: how often and how early the expected evidence appears. Whiskers are 95% confidence intervals."
          actions={
            <>
              <Segmented
                label="Split"
                value={split}
                options={runs.map((r) => {
                  const s: EvalSplit = r.provenance.split === "test" ? "test" : "dev";
                  return { value: s, label: SPLIT_LABEL[s] };
                })}
                onChange={changeSplit}
              />
              <Segmented
                label="Items"
                value={population}
                options={[
                  { value: "eligible", label: "Retrieval-eligible" },
                  { value: "all", label: "All items" },
                ]}
                onChange={setPopulation}
              />
            </>
          }
        >
          <p className="mb-4 flex flex-wrap items-center gap-2 text-sm text-muted">
            {run.label}: {population === "eligible" ? "retrieval-eligible items" : "all items"}, n ={" "}
            {formatNumber(population === "eligible" ? run.n_eligible : run.n)}.
            <SourceRef path={run.provenance.path} note="Per-arm metrics; each table cell below links its own pointer." />
          </p>
          <ArmCharts run={run} population={population} />
          <div className="mt-6 max-w-3xl">
            <LatencyChart run={run} />
          </div>
          <div className="mt-6">
            <ArmsTable run={run} population={population} />
          </div>
        </Section>
      )}

      <Section
        title="Rejected and not adopted"
        description="Negative findings are first-class results: each was measured, and the measurement said no."
      >
        <ul className="grid gap-3 lg:grid-cols-2">
          {negative.map((d) => (
            <DecisionCard key={d.id} decision={d} />
          ))}
        </ul>
      </Section>

      {run && (
        <Section title="Paired comparisons" description="Same items, two methods: the difference, its 95% confidence interval and a sign test.">
          <ComparisonsTable catalog={catalog} run={run} />
        </Section>
      )}

      <Section title="Adopted" description="Changes that stayed, with the measurement that justified them.">
        <ul className="grid gap-3 lg:grid-cols-2">
          {adopted.map((d) => (
            <DecisionCard key={d.id} decision={d} />
          ))}
        </ul>
      </Section>

      <div className="mt-8">
        <Caveats caveats={caveatsFor(catalog, "retrieval")} title="Caveats for retrieval" />
      </div>
    </div>
  );
}
