import type { TelemetryRunRow } from "@/lib/api/contracts";
import { Badge } from "@/components/ui/badge";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { Table, type Column } from "@/components/ui/table";
import { formatDateTime, formatMs, formatNumber, formatUsd } from "@/lib/format";
import Link from "next/link";
import { routeReason, runStatus, terminationState, verificationDisposition } from "@/lib/labels";
import { flagLabel, outcomeFlags, outcomeMeta, outcomeOf, rowTokens, shortId } from "@/lib/telemetry-view";

const muted = (text: string) => <span className="text-muted">{text}</span>;

function routeText(code: string | null): string {
  if (!code) return "Route not recorded";
  const h = routeReason(code);
  return h.known ? h.label : code;
}

/** Outcome as dot + label; the recorded termination state and extra flags sit underneath. */
function Status({ row }: { row: TelemetryRunRow }) {
  const key = outcomeOf({ status: row.status, termination_state: row.termination_state, disposition: row.verification_disposition });
  const outcome = outcomeMeta(key);
  // The termination line adds detail only where the outcome groups several recorded states.
  const showTerm = key === "limited" || key === "failed" || key === "cancelled";
  const status = runStatus(row.status);
  const term = row.termination_state ? terminationState(row.termination_state) : null;
  const { implied, extra } = outcomeFlags(row.termination_state, row.flags);
  const title = [
    `Status: ${status.known ? status.label : row.status}`,
    `Ended as: ${term ? (term.known ? term.label : term.code) : "not recorded"}`,
    ...implied.map((f) => `${flagLabel(f)} (${f})`),
  ].join("\n");
  return (
    <div className="flex min-w-44 flex-col items-start gap-0.5" title={title}>
      <StatusIndicator tone={outcome.tone} label={outcome.label} className="whitespace-nowrap" />
      {showTerm && term && term.label !== outcome.label && <span className="pl-3.5 text-xs text-muted">{term.known ? term.label : term.code}</span>}
      {extra.length > 0 && (
        <span className="pl-3.5">
          <Badge tone="warn" title={extra.map((f) => `${flagLabel(f)} (${f})`).join("\n")}>
            {flagLabel(extra[0])}
            {extra.length > 1 && <span className="ml-1 text-muted">+{extra.length - 1}</span>}
          </Badge>
        </span>
      )}
    </div>
  );
}

const shortTime = (iso: string): string => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
};

const columns = (href: (row: TelemetryRunRow) => string): Column<TelemetryRunRow>[] => [
  {
    key: "run",
    header: "Run",
    cell: (r) => (
      <Link
        href={href(r)}
        aria-label={`Open run ${shortId(r.id)} from ${formatDateTime(r.created_at)}`}
        className="rounded-sm font-mono text-sm text-accent-text underline-offset-2 hover:underline"
        title={r.id}
      >
        {shortId(r.id)}
      </Link>
    ),
  },
  {
    key: "time",
    header: "Time",
    cell: (r) => (
      <span className="whitespace-nowrap text-sm text-secondary" title={formatDateTime(r.created_at)}>
        {shortTime(r.created_at)}
      </span>
    ),
  },
  {
    key: "query",
    header: "Query",
    cell: (r) => (
      <div className="w-52 max-w-52">
        <p className="truncate text-sm" title={r.question}>
          {r.question}
        </p>
        <p className="truncate text-xs text-muted">{routeText(r.route_reason)}</p>
      </div>
    ),
  },
  { key: "mode", header: "Mode", cell: (r) => <span className="text-sm capitalize">{r.mode}</span> },
  { key: "status", header: "Outcome", cell: (r) => <Status row={r} /> },
  { key: "latency", header: "Latency", align: "right", cell: (r) => <span className="whitespace-nowrap text-sm">{formatMs(r.total_ms)}</span> },
  {
    key: "tokens",
    header: "Tokens in / out",
    align: "right",
    cell: (r) => (
      <span className="whitespace-nowrap text-sm" title={rowTokens(r) ?? "No model tokens"}>
        {r.tokens_in === 0 && r.tokens_out === 0 ? muted("—") : `${formatNumber(r.tokens_in)} / ${formatNumber(r.tokens_out)}`}
      </span>
    ),
  },
  {
    key: "calls",
    header: "Model / tool calls",
    align: "right",
    cell: (r) => (
      <span className="whitespace-nowrap text-sm" title={`${r.model_calls == null ? "Model calls not recorded" : `${r.model_calls} model calls`}, ${r.tool_calls} tool calls`}>
        {r.model_calls == null ? muted("—") : formatNumber(r.model_calls)} / {formatNumber(r.tool_calls)}
      </span>
    ),
  },
  { key: "cost", header: "Cost (est.)", align: "right", cell: (r) => <span className="whitespace-nowrap text-sm">{formatUsd(r.est_cost_usd)}</span> },
  {
    key: "evidence",
    header: "Evidence cited / pack",
    align: "right",
    cell: (r) => (
      <span className="whitespace-nowrap text-sm" title={`${r.evidence_count} passages in the pack, ${r.cited_count} cited${r.result_count ? `, ${r.result_count} computed results` : ""}`}>
        {`${formatNumber(r.cited_count)} / ${formatNumber(r.evidence_count)}`}
      </span>
    ),
  },
  {
    key: "verification",
    header: "Verification",
    cell: (r) => {
      if (!r.verification_disposition) return muted("Not recorded");
      const d = verificationDisposition(r.verification_disposition);
      return (
        <span className="whitespace-nowrap text-sm" title={d.description}>
          {d.label}
          {r.regenerated && <span className="block text-xs text-muted">regenerated</span>}
        </span>
      );
    },
  },
];

/**
 * Dense run explorer table: sticky header, each row opens the run (click or Enter); the Run
 * column is also a real link, so open-in-new-tab and copy work.
 */
export function RunsTable({
  rows,
  runHref,
  onOpen,
}: {
  rows: TelemetryRunRow[];
  runHref: (row: TelemetryRunRow) => string;
  onOpen?: (row: TelemetryRunRow) => void;
}) {
  return (
    <Table
      caption="Runs, newest first. Select a row to open its telemetry."
      columns={columns(runHref)}
      rows={rows}
      rowKey={(r) => r.id}
      density="compact"
      stickyHeader
      maxHeight="36rem"
      onRowClick={onOpen}
      empty="No runs match these filters."
    />
  );
}
