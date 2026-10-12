"use client";

import type { TelemetryRunDetail } from "@/lib/api/contracts";
import { useOptionalEvidenceDrawer } from "@/components/evidence/drawer-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { KeyValueList } from "@/components/ui/key-value";
import { cx } from "@/lib/cx";
import { formatMs, formatNumber, formatUsd } from "@/lib/format";
import { degradationFlag, routeReason, runMode, stopReason, type Humanized } from "@/lib/labels";
import { USAGE_KEYS, formatShare, shortId, stageSegments, usageValue } from "@/lib/telemetry-view";
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
}

function UsageCell({ usage, k }: { usage: UsageRow["usage"]; k: string }) {
  const v = usageValue(usage, k);
  return <td className="py-1 text-right tabular-nums text-primary">{v == null ? <span className="text-muted">-</span> : formatNumber(v)}</td>;
}

export function UsageCard({ detail }: { detail: Detail }) {
  const { run, agent } = detail;
  const rows: UsageRow[] = [
    { label: "Synthesis", usage: Object.keys(run.usage ?? {}).length ? run.usage : null },
    { label: "Research steps", usage: agent?.usage ?? null },
  ];
  const models = Object.entries(run.models ?? {});
  return (
    <Panel title="Model and token usage" meta={run.model ?? undefined}>
      <table className="w-full text-sm">
        <caption className="sr-only">Token usage by source</caption>
        <thead>
          <tr className="text-left text-muted">
            <th scope="col" className="pb-1.5 font-medium">Source</th>
            <th scope="col" className="pb-1.5 text-right font-medium">Calls</th>
            <th scope="col" className="pb-1.5 text-right font-medium">Input</th>
            <th scope="col" className="pb-1.5 text-right font-medium">Output</th>
            <th scope="col" className="pb-1.5 text-right font-medium">Cache read</th>
            <th scope="col" className="pb-1.5 text-right font-medium">Cache write</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-t border-border">
              <th scope="row" className="py-1 text-left font-normal text-secondary">
                {r.label}
              </th>
              {r.usage ? (
                [USAGE_KEYS.calls, USAGE_KEYS.input, USAGE_KEYS.output, USAGE_KEYS.cacheRead, USAGE_KEYS.cacheWrite].map((k) => (
                  <UsageCell key={k} usage={r.usage} k={k} />
                ))
              ) : (
                <td colSpan={5} className="py-1 text-right text-muted">
                  {r.label === "Research steps" && run.mode !== "research" ? "Not applicable (standard run)" : "Not recorded"}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      <dl className="mt-3 grid grid-cols-3 gap-3 border-t border-border pt-2.5 text-sm">
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

/** Accent shades for consecutive segments; the table carries the labels, so colour is never the only cue. */
const SHADES = ["bg-accent", "bg-accent/70", "bg-accent/45", "bg-accent/30", "bg-accent/85", "bg-accent/55"];

export function StageTiming({ detail }: { detail: Detail }) {
  const { timings, mode, total_ms } = detail.run;
  const segments = stageSegments(mode, timings ?? {});
  const firstToken = usageValue(timings, "first_token_ms");
  if (segments.length === 0) return <NotRecorded>No stage timings were recorded for this run.</NotRecorded>;
  const shade = (i: number, key: string) => (key === "other" ? "bg-border-strong" : SHADES[i % SHADES.length]);
  return (
    <div className="rounded-lg border border-border bg-surface px-4 py-3">
      <div className="flex h-3 w-full overflow-hidden rounded-sm bg-surface-sunken" role="img" aria-label="Stage timing bar; values in the table below">
        {segments.map((s, i) => (
          <div key={s.key} className={cx("h-full border-r border-surface last:border-r-0", shade(i, s.key))} style={{ width: `${s.pct}%` }} title={`${s.label}: ${formatMs(s.ms)}`} />
        ))}
      </div>
      <table className="mt-3 w-full text-sm">
        <caption className="sr-only">Stage timings for this run</caption>
        <thead>
          <tr className="text-left text-muted">
            <th scope="col" className="pb-1.5 font-medium">Stage</th>
            <th scope="col" className="pb-1.5 text-right font-medium">Duration</th>
            <th scope="col" className="pb-1.5 text-right font-medium">Share</th>
          </tr>
        </thead>
        <tbody>
          {segments.map((s, i) => (
            <tr key={s.key} className="border-t border-border">
              <th scope="row" className="py-1 text-left font-normal text-secondary">
                <span className="flex items-center gap-2">
                  <span aria-hidden className={cx("h-2.5 w-2.5 shrink-0 rounded-sm", shade(i, s.key))} />
                  {s.label}
                </span>
              </th>
              <td className="py-1 text-right tabular-nums text-primary">{formatMs(s.ms)}</td>
              <td className="py-1 text-right tabular-nums text-muted">{formatShare(s.pct)}</td>
            </tr>
          ))}
          <tr className="border-t border-border-strong">
            <th scope="row" className="py-1 text-left font-medium text-primary">
              Total
            </th>
            <td className="py-1 text-right font-medium tabular-nums text-primary">{formatMs(total_ms)}</td>
            <td />
          </tr>
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted">
        {firstToken == null ? "First token: not recorded." : `First token ${formatMs(firstToken)} after synthesis started.`} Stages a run did not
        record are omitted, not shown as zero.
      </p>
    </div>
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
