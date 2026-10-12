import type { TelemetryRunDetail, TelemetryToolCall, VerificationAttemptSummary } from "@/lib/api/contracts";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { DevDetails } from "@/components/ui/disclosure";
import { Table, type Column } from "@/components/ui/table";
import { cx } from "@/lib/cx";
import { glossaryTitle } from "@/lib/eval-view";
import { formatMs, formatNumber } from "@/lib/format";
import { verificationDisposition, verificationFailure } from "@/lib/labels";
import {
  buildTimeline,
  formatOffset,
  isRedacted,
  timelineResultCounts,
  toolResultCount,
  toolStatusLabel,
  toolStatusTone,
  toolStepLabel,
  type TimelineStep, type TimelineStepKind } from "@/lib/telemetry-view";
import { NotRecorded, Panel } from "./stat-tile";

type Detail = TelemetryRunDetail;


/** Marker shape per step family; the title always names the step, so the marker is decorative. */
function markerClass(kind: TimelineStepKind): string {
  if (kind === "error") return "bg-danger";
  if (kind === "warning" || kind === "draft_reset") return "bg-warn";
  if (kind === "tool" || kind === "analytics" || kind === "retrieval") return "bg-accent";
  if (kind === "final" || kind === "done") return "bg-success";
  return "bg-border-strong";
}

function StepRow({ step }: { step: TimelineStep }) {
  const dur = step.duration_ms;
  return (
    <li className="grid grid-cols-[6.5rem_1rem_minmax(0,1fr)_auto] items-start gap-x-2 border-t border-border py-1.5 first:border-t-0">
      <span className="pt-px text-right font-mono text-xs tabular-nums text-muted">{formatOffset(step.t_ms)}</span>
      <span aria-hidden className="flex justify-center pt-1.5">
        <span className={cx("h-2 w-2 rounded-full", markerClass(step.kind))} />
      </span>
      <div className="min-w-0">
        <p className="text-sm font-medium text-primary">{step.title}</p>
        {step.detail && <p className="truncate text-xs text-muted" title={step.detail}>{step.detail}</p>}
      </div>
      <div className="flex items-center gap-2 pt-px">
        {step.status && <Badge tone={toolStatusTone(step.status)} title={step.status}>{toolStatusLabel(step.status)}</Badge>}
        {dur != null && <span className="whitespace-nowrap text-xs tabular-nums text-muted">{formatMs(dur)}</span>}
      </div>
    </li>
  );
}

export function RunTimeline({ detail }: { detail: Detail }) {
  const steps = buildTimeline(detail.timeline, detail.run.mode);
  if (steps.length === 0) return <NotRecorded>No observable events were recorded for this run.</NotRecorded>;
  return (
    <Card padding="none" className="px-4 py-2">
      <ol aria-label="Observable run timeline">
        {steps.map((s) => (
          <StepRow key={s.id} step={s} />
        ))}
      </ol>
    </Card>
  );
}

const toolColumns = (counts: Map<string, number>): Column<TelemetryToolCall>[] => [
  {
    key: "step",
    header: "Step",
    width: "7.5rem",
    cell: (t) => <span className="whitespace-nowrap text-sm tabular-nums">{toolStepLabel(t)}</span>,
  },
  { key: "tool", header: "Tool", cell: (t) => <span className="font-mono text-sm">{t.tool}</span> },
  {
    key: "status",
    header: "Status",
    cell: (t) => (
      <span className="flex flex-col items-start gap-0.5">
        <Badge tone={toolStatusTone(t.status)} title={t.status}>{toolStatusLabel(t.status)}</Badge>
        {t.error_code && <span className="font-mono text-xs text-muted">{t.error_code}</span>}
      </span>
    ),
  },
  { key: "dur", header: "Duration", align: "right", cell: (t) => <span className="whitespace-nowrap text-sm">{formatMs(t.duration_ms)}</span> },
  {
    key: "results",
    header: "Results",
    align: "right",
    cell: (t) => {
      const n = toolResultCount(t, counts);
      return (
      <span className="whitespace-nowrap text-sm">
        {n == null ? <span className="text-muted" title="This tool returns a non-list result">—</span> : formatNumber(n)}
        {t.total_matches != null && <span className="block text-xs text-muted">{`of ${formatNumber(t.total_matches)} matches`}</span>}
        {t.truncated && <span className="block text-xs text-warn">Truncated</span>}
      </span>
      );
    },
  },
  {
    key: "args",
    header: "Arguments",
    cell: (t) =>
      isRedacted(t) ? (
        <Badge tone="info" title="Arguments were redacted by the governance audit">
          Redacted
        </Badge>
      ) : (
        <DevDetails summary="Sanitized arguments" data={t.args} />
      ),
  },
  {
    key: "warnings",
    header: "Warnings",
    cell: (t) =>
      t.warnings.length === 0 ? (
        <span className="text-sm text-muted">None</span>
      ) : (
        <span className="flex flex-wrap gap-1">
          {t.warnings.map((w) => (
            <Badge key={w} tone="warn">
              {w}
            </Badge>
          ))}
        </span>
      ),
  },
];

export function ToolCalls({ detail }: { detail: Detail }) {
  if (detail.tools.length === 0) {
    const text =
      detail.run.mode !== "research"
        ? "Standard runs make no research tool calls; the single retrieval is shown under Retrieval."
        : detail.agent
          ? "No audited research tool calls were made in this run."
          : "Not recorded for this run.";
    return <NotRecorded>{text}</NotRecorded>;
  }
  return (
    <Table
      caption="Audited research tool calls, in order"
      columns={toolColumns(timelineResultCounts(detail.timeline))}
      rows={detail.tools}
      rowKey={(t) => `${t.step}-${t.call_index}-${t.tool}`}
      density="compact"
    />
  );
}

const label = (h: { known: boolean; label: string; code: string }): string => (h.known ? h.label : h.code);

const VERIFY_COLUMNS: Column<VerificationAttemptSummary>[] = [
  { key: "attempt", header: "Attempt", width: "5rem", cell: (v) => <span className="tabular-nums">{v.attempt}</span> },
  {
    key: "disp",
    header: "Disposition",
    cell: (v) => {
      const h = verificationDisposition(v.disposition);
      return (
        <span className="flex flex-col items-start gap-0.5">
          <Badge tone={h.tone ?? "neutral"} title={v.disposition}>
            {label(h)}
          </Badge>
          <span className="text-xs text-muted">{v.passed ? "Passed" : "Did not pass"}</span>
        </span>
      );
    },
  },
  {
    key: "cites",
    header: <span title="Citation references the verifier checked in this attempt, including repeats">References checked</span>,
    align: "right",
    cell: (v) => formatNumber(v.citations),
  },
  { key: "repairs", header: "Repairs", align: "right", cell: (v) => formatNumber(v.repairs_n) },
  {
    key: "failures",
    header: "Failure categories",
    cell: (v) =>
      v.failure_categories.length === 0 ? (
        <span className="text-sm text-muted">None</span>
      ) : (
        <ul className="text-sm">
          {v.failure_categories.map((c) => (
            <li key={c}>{label(verificationFailure(c))}</li>
          ))}
        </ul>
      ),
  },
  {
    key: "rejected",
    header: "Rejected (reasons only)",
    cell: (v) =>
      v.rejected.length === 0 ? (
        <span className="text-sm text-muted">None</span>
      ) : (
        <ul className="text-sm">
          {v.rejected.map((r, i) => (
            <li key={`${r.reason}-${i}`}>
              {label(verificationFailure(r.reason))}
              {r.section && <span className="text-muted">{` in "${r.section}"`}</span>}
            </li>
          ))}
        </ul>
      ),
  },
];

export function VerificationAttempts({ detail }: { detail: Detail }) {
  if (detail.verification.length === 0) {
    return <NotRecorded>Not recorded for this run: no verification attempts were logged.</NotRecorded>;
  }
  return (
    <Table
      caption="Verification attempts"
      columns={VERIFY_COLUMNS}
      rows={detail.verification}
      rowKey={(v) => String(v.attempt)}
      density="compact"
    />
  );
}

const SUB_STAGES: { key: string; label: string }[] = [
  { key: "embed_ms", label: "Query embedding" },
  { key: "lexical_prep_ms", label: "Lexical query prep" },
  { key: "lexical_ms", label: "Lexical search" },
  { key: "dense_ms", label: "Dense search" },
  { key: "fusion_ms", label: "Fusion (reciprocal-rank)" },
  { key: "total_ms", label: "Total" },
];

type SubStage = (typeof SUB_STAGES)[number];

const SUB_STAGE_COLUMNS = (timings: Record<string, number>): Column<SubStage>[] => {
  const strong = (st: SubStage, text: string) => (st.key === "total_ms" ? <span className="font-medium">{text}</span> : text);
  return [
    { key: "stage", header: "Stage", cell: (st) => strong(st, st.label) },
    { key: "ms", header: "Duration", align: "right", cell: (st) => strong(st, formatMs(timings[st.key])) },
  ];
};

type TopFinal = NonNullable<Detail["retrieval"]>["top_final"][number];

const rank = (v: number | null | undefined): string => (v == null ? "-" : `#${v}`);

const TOP_COLUMNS: Column<TopFinal>[] = [
  { key: "rank", header: "Rank", width: "3.5rem", cell: (r) => <span className="tabular-nums">{r.rank}</span> },
  { key: "handle", header: "Handle", cell: (r) => <span className="break-all font-mono text-xs">{r.handle}</span> },
  { key: "lex", header: "Lexical", align: "right", cell: (r) => rank(r.lanes.lexical) },
  { key: "dense", header: "Dense", align: "right", cell: (r) => rank(r.lanes.dense) },
  { key: "rrf", header: <span title={glossaryTitle("rrf")}>RRF score</span>, align: "right", cell: (r) => <span className="font-mono text-xs">{r.rrf.toFixed(4)}</span> },
];

export function RetrievalPanel({ detail }: { detail: Detail }) {
  const r = detail.retrieval;
  if (!r) {
    const text =
      detail.run.mode === "research"
        ? "No retrieval trace: research runs search through research steps, listed under Tool calls."
        : "Not recorded for this run: retrieval traces were logged only for later standard runs.";
    return <NotRecorded>{text}</NotRecorded>;
  }
  const lanes: [string, number][] = [
    ["Lexical", r.lanes.lexical],
    ["Dense", r.lanes.dense],
    ["Fused", r.lanes.fused],
    ["Final", r.lanes.final],
  ];
  return (
    <div className="grid gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <div className="flex flex-col gap-3">
        <Panel title="Candidates per lane" meta={`${formatNumber(r.active_versions)} active source versions`}>
          <dl className="grid grid-cols-4 gap-3">
            {lanes.map(([l, n]) => (
              <div key={l}>
                <dt className="text-sm text-muted">{l}</dt>
                <dd className="mt-0.5 text-lg font-semibold tabular-nums text-primary">{formatNumber(n)}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 border-t border-border pt-2 text-sm text-secondary">
            Embedding cache:{" "}
            <span className="font-medium text-primary">{r.embedding_cache_hit == null ? "Not recorded" : r.embedding_cache_hit ? "Hit" : "Miss"}</span>
          </p>
        </Panel>
        <Table
          caption="Sub-stage timings"
          showCaption
          columns={SUB_STAGE_COLUMNS(r.timings)}
          rows={SUB_STAGES.filter((st) => typeof r.timings[st.key] === "number")}
          rowKey={(st) => st.key}
          density="compact"
        />
      </div>
      <Table
        caption="Top final evidence passages, with each lane's rank"
        showCaption
        columns={TOP_COLUMNS}
        rows={r.top_final}
        rowKey={(t) => `${t.rank}-${t.handle}`}
        density="compact"
        empty="No final passages recorded."
      />
    </div>
  );
}
