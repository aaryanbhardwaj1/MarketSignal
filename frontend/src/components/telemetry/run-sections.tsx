"use client";

import type { ReactNode } from "react";
import type { TelemetryRunDetail } from "@/lib/api/contracts";
import { useOptionalEvidenceDrawer } from "@/components/evidence/drawer-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { KeyValueList } from "@/components/ui/key-value";
import { Table, type Column } from "@/components/ui/table";
import { formatMs, formatNumber, formatUsd } from "@/lib/format";
import { degradationFlag, routeReason, runMode, stopReason, type Humanized } from "@/lib/labels";
import { USAGE_KEYS, shortId, usageValue } from "@/lib/telemetry-view";
import { NotRecorded, Panel } from "./stat-tile";

type Detail = TelemetryRunDetail;

/** Known code → label with the raw code beside it (developer page). */
function Coded({ h }: { h: Humanized }) {
  if (!h.code) return <span className="text-muted">Not recorded</span>;
  return (
    <span>
      {h.known ? h.label : h.code}
      {h.known && <span className="ml-1.5 font-mono text-xs text-muted">{h.code}</span>}
    </span>
  );
}

const modeText = (code: string | undefined): string => {
  if (!code) return "Not recorded";
  const h = runMode(code);
  return h.known ? h.label : code;
};

export function RouteCard({ route }: { route: Detail["run"]["route"] }) {
  const recorded = Boolean(route && (route.decided || route.reason));
  return (
    <Panel title="Route decision" meta="How the run mode was chosen">
      {!recorded ? (
        <NotRecorded>Not recorded for this run. Route decisions were logged only for later runs.</NotRecorded>
      ) : (
        <KeyValueList
          columns={2}
          items={[
            { label: "Requested", value: modeText(route.requested) },
            { label: "Role default", value: modeText(route.persona_default) },
            { label: "Decided", value: <span className="font-medium">{modeText(route.decided)}</span> },
            { label: "Reason", value: <Coded h={routeReason(route.reason)} /> },
            { label: "Task type", value: route.task_type ? <span className="font-mono text-sm">{route.task_type}</span> : <span className="text-muted">Not recorded</span> },
            {
              label: "Cues",
              value:
                route.cues && route.cues.length > 0 ? (
                  <span className="flex flex-wrap gap-1">
                    {route.cues.map((c) => (
                      <Badge key={c}>{c}</Badge>
                    ))}
                  </span>
                ) : (
                  <span className="text-muted">None</span>
                ),
            },
          ]}
        />
      )}
    </Panel>
  );
}

export function ResearchCard({ detail }: { detail: Detail }) {
  const a = detail.agent;
  const isResearch = detail.run.mode === "research";
  return (
    <Panel title="Research steps" meta={a ? `${formatMs(a.duration_ms)} total` : undefined}>
      {!a ? (
        <NotRecorded>
          {isResearch ? "Not recorded for this run." : "Not applicable: standard runs perform one retrieval and no research steps."}
        </NotRecorded>
      ) : (
        <>
          <KeyValueList
            columns={2}
            items={[
              { label: "Stop reason", value: <Coded h={stopReason(a.stop_reason)} /> },
              { label: "Steps / tool calls", value: `${formatNumber(a.steps)} / ${formatNumber(a.tool_calls)}` },
              { label: "Tool errors", value: formatNumber(a.tool_errors) },
              { label: "Evidence pool", value: `${formatNumber(a.pool_size)} passages` },
              {
                label: "Planner judged sufficient",
                value: a.sufficient == null ? <span className="text-muted">Not recorded (planner did not run)</span> : a.sufficient ? "Yes" : "No",
              },
              { label: "Open gaps", value: formatNumber(a.gap_count) },
            ]}
          />
          {a.flags.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1 border-t border-border pt-2.5">
              {a.flags.map((f) => (
                <Badge key={f} tone="warn" title={f}>
                  {degradationFlag(f).known ? degradationFlag(f).label : f}
                </Badge>
              ))}
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

interface UsageRow {
  label: string;
  usage: Record<string, number> | null | undefined;
  missing: string;
}

function usageCell(k: string): (r: UsageRow) => ReactNode {
  return function UsageCell(r: UsageRow) {
    const v = usageValue(r.usage, k);
    return v == null ? <span className="text-muted">-</span> : formatNumber(v);
  };
}

const USAGE_COLUMNS: Column<UsageRow>[] = [
  {
    key: "source",
    header: "Source",
    cell: (r) => (
      <span className="flex flex-col">
        <span className="text-secondary">{r.label}</span>
        {!r.usage && <span className="text-xs text-muted">{r.missing}</span>}
      </span>
    ),
  },
  { key: "calls", header: "Calls", align: "right", cell: usageCell(USAGE_KEYS.calls) },
  { key: "in", header: "Input", align: "right", cell: usageCell(USAGE_KEYS.input) },
  { key: "out", header: "Output", align: "right", cell: usageCell(USAGE_KEYS.output) },
  { key: "cr", header: "Cache read", align: "right", cell: usageCell(USAGE_KEYS.cacheRead) },
  { key: "cw", header: "Cache write", align: "right", cell: usageCell(USAGE_KEYS.cacheWrite) },
];

export function UsageCard({ detail }: { detail: Detail }) {
  const { run, agent } = detail;
  const rows: UsageRow[] = [
    { label: "Synthesis", usage: Object.keys(run.usage ?? {}).length ? run.usage : null, missing: "Not recorded" },
    {
      label: "Research steps",
      usage: agent?.usage ?? null,
      missing: run.mode !== "research" ? "Not applicable (standard run)" : "Not recorded",
    },
  ];
  const models = Object.entries(run.models ?? {});
  return (
    <Panel title="Model and token usage" meta={run.model ?? undefined}>
      <Table caption="Token usage by source" columns={USAGE_COLUMNS} rows={rows} rowKey={(r) => r.label} density="compact" />
      <dl className="mt-3 grid grid-cols-3 gap-3 text-sm">
        <div>
          <dt className="text-muted">Model calls</dt>
          <dd className="font-medium tabular-nums text-primary">{run.model_calls == null ? "Not recorded" : formatNumber(run.model_calls)}</dd>
        </div>
        <div>
          <dt className="text-muted">Tokens in / out</dt>
          <dd className="font-medium tabular-nums text-primary">
            {formatNumber(run.tokens_in)} / {formatNumber(run.tokens_out)}
          </dd>
        </div>
        <div>
          <dt className="text-muted">Estimated cost (list prices)</dt>
          <dd className="font-medium tabular-nums text-primary">{formatUsd(run.est_cost_usd)}</dd>
        </div>
      </dl>
      {models.length > 0 && (
        <p className="mt-2 text-xs text-muted">
          Models: {models.map(([role, m]) => `${role} ${m}`).join(" · ")}
        </p>
      )}
    </Panel>
  );
}

export function AnalyticsResults({ ids }: { ids: string[] }) {
  const drawer = useOptionalEvidenceDrawer();
  if (ids.length === 0) return <NotRecorded>No computed results were used by this run.</NotRecorded>;
  return (
    <ul className="flex flex-wrap gap-2">
      {ids.map((id) => (
        <li key={id}>
          <Button variant="secondary" size="sm" onClick={() => drawer?.openResult(id)} disabled={!drawer}>
            Open result <span className="font-mono text-xs text-muted">{shortId(id)}</span>
          </Button>
        </li>
      ))}
    </ul>
  );
}
