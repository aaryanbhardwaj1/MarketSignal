"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { BarList } from "@/components/ui/bar-list";
import { Callout } from "@/components/ui/callout";
import { Card } from "@/components/ui/card";
import { Section } from "@/components/ui/section";
import { Table, type Column } from "@/components/ui/table";
import type { EvalCatalog, EvalMetric, EvalRunId } from "@/lib/api/contracts";
import {
  glossaryTitle,
  type GlossaryKey,
  DECISION_OUTCOME,
  caveatsFor,
  deltaVerdict,
  formatCi,
  formatEvalValue,
  formatSigned,
  sourceLocator,
} from "@/lib/eval-view";
import { formatMs, formatNumber } from "@/lib/format";
import { Caveats } from "./caveats";
import { MetricGlossary } from "./metric-glossary";
import { DeltaCell, MetricCell, MetricSource, Segmented, SourceRef } from "./metric-bits";

type RetrievalRun = EvalCatalog["retrieval"]["runs"][number];
type Arm = RetrievalRun["arms"][number];
type Comparison = EvalCatalog["retrieval"]["comparisons"][number];
type Decision = EvalCatalog["retrieval"]["decisions"][number];
type Population = "eligible" | "all";

const ARM_METRICS = [
  { key: "hit@1", header: "Hit@1", gloss: "hit" },
  { key: "recall@10", header: "Recall@10", gloss: "recall" },
  { key: "mrr", header: "MRR", gloss: "mrr" },
] as const;

/** Column header with its glossary definition on hover. */
const abbr = (text: string, key: GlossaryKey) => <span title={glossaryTitle(key)}>{text}</span>;

const splitLabel = (run: RetrievalRun) => (run.provenance.split === "test" ? "Held-out test" : "Dev");

function armLabel(run: RetrievalRun | undefined, arm: string): string {
  return run?.arms.find((a) => a.arm === arm)?.label ?? arm;
}

function findComparison(c: EvalCatalog, runId: EvalRunId, a: string, b: string): Comparison | undefined {
  return c.retrieval.comparisons.find((x) => x.run_id === runId && x.a === a && x.b === b);
}

const metricOf = (cmp: Comparison | undefined, suffix: string): EvalMetric | undefined =>
  cmp?.metrics.find((m) => m.id.endsWith(`.${suffix}`));

/** The headline reading: does hybrid beat vector-only on held-out data, and what did the reranker do? */
function Conclusion({ catalog, testRun }: { catalog: EvalCatalog; testRun: RetrievalRun | undefined }) {
  if (!testRun) return null;
  const hybridArm = testRun.arms.find((a) => a.is_default);
  const dense = findComparison(catalog, testRun.run_id, "dense", hybridArm?.arm ?? "hybrid");
  const rerank = findComparison(catalog, testRun.run_id, hybridArm?.arm ?? "hybrid", "hybrid-rerank");
  const d1 = metricOf(dense, "d_recall@10");
  const d2 = metricOf(rerank, "d_recall@10");
  const v1 = d1 ? deltaVerdict(d1) : null;
  const v2 = d2 ? deltaVerdict(d2) : null;
  return (
    <div className="flex flex-col gap-3">
      {d1 && v1 && (
        <Callout
          tone="info"
          title={
            v1.distinguishable && v1.tone === "success"
              ? `Hybrid retrieval recovered more of the expected evidence than vector-only search on the held-out split.`
              : `Hybrid and vector-only retrieval were not distinguishable on the held-out split.`
          }
        >
          {d1.label}: <span className="font-medium tabular-nums text-primary">{formatSigned(d1.value, d1.unit)}</span> (
          {formatCi(d1, { signed: true })}, n = {formatNumber(d1.n)}). Hit@10 changed on{" "}
          {formatNumber(dense?.hit_at_10.gains)} items for the better and {formatNumber(dense?.hit_at_10.losses)} for the
          worse. <MetricSource source={d1.source} />
        </Callout>
      )}
      {d2 && v2 && v2.distinguishable && v2.tone === "warn" && (
        <Callout tone="warn" title="Negative finding: the reranker lowered held-out evidence recall, so it was not adopted.">
          {d2.label}: <span className="font-medium tabular-nums text-primary">{formatSigned(d2.value, d2.unit)}</span> (
          {formatCi(d2, { signed: true })}, n = {formatNumber(d2.n)}). It looked better on dev; see Decisions below.{" "}
          <MetricSource source={d2.source} />
        </Callout>
      )}
    </div>
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
  return (
    <Card as="li" padding="sm">
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
    </Card>
  );
}

export function RetrievalTab({ catalog }: { catalog: EvalCatalog }) {
  const runs = catalog.retrieval.runs;
  const testRun = runs.find((r) => r.provenance.split === "test");
  const [runId, setRunId] = useState<EvalRunId | undefined>(testRun?.run_id ?? runs[0]?.run_id);
  const [population, setPopulation] = useState<Population>("eligible");
  const run = runs.find((r) => r.run_id === runId) ?? runs[0];
  const negative = catalog.retrieval.decisions.filter((d) => d.outcome !== "adopted");
  const adopted = catalog.retrieval.decisions.filter((d) => d.outcome === "adopted");

  return (
    <div>
      <Conclusion catalog={catalog} testRun={testRun} />
      <div className="mt-4">
        <MetricGlossary keys={["hit", "recall", "mrr", "eligible", "ci", "pp", "rrf", "bge", "p50"]} />
      </div>

      {run && (
        <Section
          title="Retrieval methods compared"
          description="Each method retrieves passages for the same questions; scores measure how early the expected evidence appears."
          actions={
            <>
              <Segmented
                label="Split"
                value={run.run_id}
                options={runs.map((r) => ({ value: r.run_id, label: splitLabel(r) }))}
                onChange={setRunId}
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
          <ArmsTable run={run} population={population} />
          <Card padding="sm" className="mt-4">
            <p className="mb-3 text-sm font-medium text-secondary">Recall@10 by method ({splitLabel(run).toLowerCase()})</p>
            <BarList
              ariaLabel={`Recall@10 by retrieval method, ${run.label}`}
              max={1}
              items={run.arms.map((a) => ({
                label: a.label,
                value: a[population]["recall@10"]?.value ?? 0,
                display: formatEvalValue(a[population]["recall@10"]?.value, "ratio"),
                emphasis: a.is_default,
              }))}
            />
          </Card>
        </Section>
      )}

      {run && (
        <Section title="Paired comparisons" description="Same items, two methods: the difference and its 95% confidence interval.">
          <ComparisonsTable catalog={catalog} run={run} />
        </Section>
      )}

      <Section
        title="Decisions"
        description="What was adopted and what was rejected. Negative findings are kept on the record alongside the adopted changes."
      >
        <h3 className="mb-2 text-base font-semibold text-primary">Negative findings</h3>
        <ul className="grid gap-3 lg:grid-cols-2">
          {negative.map((d) => (
            <DecisionCard key={d.id} decision={d} />
          ))}
        </ul>
        <h3 className="mb-2 mt-6 text-base font-semibold text-primary">Adopted</h3>
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
