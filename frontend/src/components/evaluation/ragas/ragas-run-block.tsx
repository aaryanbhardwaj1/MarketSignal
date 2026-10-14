"use client";

import { useState } from "react";
import { GroupedBarChart } from "@/components/charts";
import { Select } from "@/components/ui/form-controls";
import type { EvalCatalog, RagasCaveat, RagasConfiguration, RagasMetricDefinition, RagasRun } from "@/lib/api/contracts";
import { formatEvalValue, sourceLocator } from "@/lib/eval-view";
import { formatDateTime, formatNumber, humanize } from "@/lib/format";
import {
  comparisonTakeaway,
  computedSummary,
  configurationComparison,
  configurationLabel,
  histogramView,
  metricResult,
  shortMetricLabel,
} from "@/lib/views/ragas";
import { RagasSource } from "./ragas-source";

const ratio = (v: number) => formatEvalValue(v, "ratio");
const count = (v: number) => formatNumber(v);

export const PACK_PRECISION_NOTE =
  "Low ID precision over the evidence pack is expected: a pack holds many passages and only a few of them are gold.";

function RunMeta({ run, catalog }: { run: RagasRun; catalog: EvalCatalog }) {
  const scored = catalog.failure_runs.find((r) => r.run_id === run.source_run)?.label ?? run.source_run;
  const dataset =
    run.dataset.version && run.dataset.version !== run.dataset.name ? `${run.dataset.name} (${run.dataset.version})` : run.dataset.name;
  return (
    <dl className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted">
      <div className="flex gap-1.5">
        <dt>Scored run</dt>
        <dd className="text-secondary">{scored}</dd>
      </div>
      <div className="flex gap-1.5">
        <dt>Dataset</dt>
        <dd className="font-mono text-secondary">{dataset}</dd>
      </div>
      <div className="flex gap-1.5">
        <dt>Split</dt>
        <dd className="text-secondary">{run.split ?? "Not split"}</dd>
      </div>
      <div className="flex gap-1.5">
        <dt>Computed</dt>
        <dd className="tabular-nums text-secondary">{formatDateTime(run.created_at)}</dd>
      </div>
    </dl>
  );
}

function SampleNote({ config, multi }: { config: RagasConfiguration; multi: boolean }) {
  const reasons = config.excluded_reasons.map((r) => `${humanize(r.reason).toLowerCase()} ${formatNumber(r.n)}`).join(", ");
  return (
    <li className="tabular-nums">
      {multi && <span className="font-medium text-secondary">{configurationLabel(config.name)}: </span>}
      {formatNumber(config.n_samples)} items scored
      {config.n_excluded > 0 && `; ${formatNumber(config.n_excluded)} excluded (${reasons})`}
    </li>
  );
}

function ConfigValue({ config, def, multi }: { config: RagasConfiguration; def: RagasMetricDefinition; multi: boolean }) {
  const summary = computedSummary(config, def.key);
  const result = metricResult(config, def.key);
  return (
    <div className="min-w-0" data-config={config.name}>
      {multi && <p className="text-xs text-muted">{configurationLabel(config.name)}</p>}
      {summary ? (
        <>
          <p className="text-xl font-semibold tabular-nums text-primary" data-metric-mean={def.key}>
            {ratio(summary.mean)}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs tabular-nums text-muted">
            <span>median {ratio(summary.median)}</span>
            <span>n {count(summary.n)}</span>
            {summary.n_nan > 0 && <span>undefined {count(summary.n_nan)}</span>}
            {result && <RagasSource path={result.source.path} locator={result.source.pointer} />}
          </p>
        </>
      ) : (
        <p className="text-sm text-muted">Not computed</p>
      )}
    </div>
  );
}

function MetricTile({ run, def }: { run: RagasRun; def: RagasMetricDefinition }) {
  const multi = run.configurations.length > 1;
  return (
    <li className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4">
      <div>
        <p className="text-sm font-medium text-primary">{def.label}</p>
        <p className="mt-0.5 text-xs text-muted">{def.what_it_measures}</p>
      </div>
      <div className="mt-auto flex gap-6">
        {run.configurations.map((c) => (
          <ConfigValue key={c.name} config={c} def={def} multi={multi} />
        ))}
      </div>
    </li>
  );
}

function DistributionChart({ run, defs }: { run: RagasRun; defs: RagasMetricDefinition[] }) {
  const [key, setKey] = useState(defs[0]?.key ?? "");
  const def = defs.find((d) => d.key === key) ?? defs[0];
  if (!def) return null;
  const views = run.configurations.map((c) => ({ name: configurationLabel(c.name), view: histogramView(computedSummary(c, def.key)) }));
  const categories = views.find((v) => v.view.categories.length > 0)?.view.categories ?? [];
  const series = views.filter((v) => v.view.counts.length === categories.length).map((v) => ({ name: v.name, values: v.view.counts }));
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-primary">Score distribution</p>
          <p className="text-xs text-muted">Stored histogram bins, items per score band.</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-muted">
          Metric
          <Select
            controlSize="sm"
            value={def.key}
            onChange={(e) => setKey(e.target.value)}
            options={defs.map((d) => ({ value: d.key, label: d.label }))}
            className="min-w-64"
          />
        </label>
      </div>
      <GroupedBarChart
        className="mt-3"
        categories={categories}
        series={series}
        format={count}
        height={200}
        ariaLabel={`${def.label}: items per score band, ${run.title}`}
        caption={`${def.label}. Bars count items whose score falls in each band.`}
      />
    </div>
  );
}

function ConfigurationComparison({ run, defs }: { run: RagasRun; defs: RagasMetricDefinition[] }) {
  const rows = configurationComparison(run, defs);
  if (rows.length === 0) return null;
  const takeaway = comparisonTakeaway(rows);
  const names = rows[0].values.map((v) => configurationLabel(v.configuration));
  const shortLabels = rows.map((r) => shortMetricLabel(defs.find((d) => d.key === r.key) ?? r));
  return (
    <div className="rounded-lg border border-border bg-surface p-4" data-testid="ragas-comparison">
      <p className="text-sm font-medium text-primary">{names.join(" vs ")}</p>
      {takeaway && <p className="mt-0.5 text-sm text-secondary">{takeaway}</p>}
      <GroupedBarChart
        className="mt-3"
        categories={shortLabels}
        series={names.map((name, i) => ({ name, values: rows.map((r) => r.values[i].mean) }))}
        format={ratio}
        height={240}
        showValues={false}
        ariaLabel={`Mean offline RAGAS scores, ${names.join(" vs ")}`}
        caption="Mean score per metric and configuration over the same items. Exact values are in the tiles above."
      />
    </div>
  );
}

function ReconciliationCard({ caveat }: { caveat: RagasCaveat }) {
  return (
    <div role="note" className="rounded-lg border border-border bg-canvas p-4" data-caveat={caveat.id}>
      <p className="text-sm font-medium text-primary">Reconciling with the historical recall figure</p>
      <p className="mt-1 text-sm text-secondary">{caveat.text}</p>
      <ul className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2">
        {caveat.metrics.map((m) => (
          <li key={m.id} className="min-w-0">
            <p className="text-xs text-muted">{m.label}</p>
            <p className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-md font-semibold tabular-nums text-primary">{formatEvalValue(m.value, m.unit)}</span>
              {m.n != null && <span className="text-xs tabular-nums text-muted">n {formatNumber(m.n)}</span>}
              <RagasSource path={m.source.path} locator={sourceLocator(m.source)} />
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RagasRunBlock({
  run,
  defs,
  caveats,
  catalog,
}: {
  run: RagasRun;
  defs: RagasMetricDefinition[];
  caveats: RagasCaveat[];
  catalog: EvalCatalog;
}) {
  const multi = run.configurations.length > 1;
  const reconciliation = caveats.filter((c) => c.applies_to.includes(run.id) && c.metrics.length > 0);
  const hasPackPrecision = defs.some((d) => d.key === "id_context_precision_pack");
  return (
    <article aria-labelledby={`${run.id}-title`} className="flex flex-col gap-4" data-run={run.id}>
      <header>
        <h4 id={`${run.id}-title`} className="text-md font-semibold text-primary">
          {run.title}
        </h4>
        <RunMeta run={run} catalog={catalog} />
        <ul className="mt-1 text-sm text-muted">
          {run.configurations.map((c) => (
            <SampleNote key={c.name} config={c} multi={multi} />
          ))}
        </ul>
      </header>
      <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {defs.map((d) => (
          <MetricTile key={d.key} run={run} def={d} />
        ))}
      </ul>
      {hasPackPrecision && <p className="text-sm text-muted">{PACK_PRECISION_NOTE}</p>}
      <DistributionChart run={run} defs={defs} />
      <ConfigurationComparison run={run} defs={defs} />
      {reconciliation.map((c) => (
        <ReconciliationCard key={c.id} caveat={c} />
      ))}
    </article>
  );
}
