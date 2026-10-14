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

/** Verification result in words, with a regeneration note. */
function verificationText(row: TelemetryRunRow): { label: string; description?: string } {
  if (!row.verification_disposition) return { label: "Verification not recorded" };
  const d = verificationDisposition(row.verification_disposition);
  return { label: `${d.label}${row.regenerated ? " · Regenerated" : ""}`, description: d.description };
}

/**
 * Outcome as dot + label, the verification result underneath (+ a flag badge); the recorded
 * status, termination state, verification detail and implied flags are in the tooltip.
 */
function Status({ row }: { row: TelemetryRunRow }) {
  const key = outcomeOf({ status: row.status, termination_state: row.termination_state, disposition: row.verification_disposition });
  const outcome = outcomeMeta(key);
  const status = runStatus(row.status);
  const term = row.termination_state ? terminationState(row.termination_state) : null;
  const { implied, extra } = outcomeFlags(row.termination_state, row.flags);
  const verification = verificationText(row);
  const title = [
    `Status: ${status.known ? status.label : row.status}`,
    `Ended as: ${term ? (term.known ? term.label : term.code) : "not recorded"}`,
    `Verification: ${verification.label}${verification.description ? ` (${verification.description})` : ""}`,
    ...implied.map((f) => `${flagLabel(f)} (${f})`),
  ].join("\n");
  return (
    <div className="flex flex-col items-start gap-0.5" title={title}>
      <StatusIndicator tone={outcome.tone} label={outcome.label} className="whitespace-nowrap" />
      <span className="pl-3.5 text-xs whitespace-nowrap text-muted">{verification.label}</span>
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

/** Compact run time ("Oct 14, 13:55"); the full date and time are in the tooltip. */
export const shortTime = (iso: string): string => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
};

const MODE_LABEL: Readonly<Record<string, string>> = { standard: "Standard", research: "Research" };
const modeLabel = (mode: string): string => MODE_LABEL[mode] ?? mode;

const columns = (href: (row: TelemetryRunRow) => string): Column<TelemetryRunRow>[] => [
  {
    key: "run",
    header: "Run",
    cell: (r) => (
      <div className="whitespace-nowrap">
        <Link
          href={href(r)}
          aria-label={`Open run ${shortId(r.id)} from ${formatDateTime(r.created_at)}`}
          className="rounded-sm font-mono text-sm text-accent-text underline-offset-2 hover:underline"
          title={r.id}
        >
          {shortId(r.id)}
        </Link>
        <p className="text-xs text-muted tabular-nums" title={formatDateTime(r.created_at)}>
          {shortTime(r.created_at)}
        </p>
      </div>
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
        <p className="truncate text-xs text-muted" title={`${modeLabel(r.mode)} mode · ${routeText(r.route_reason)}`}>
          {modeLabel(r.mode)} · {routeText(r.route_reason)}
        </p>
      </div>
    ),
  },
  { key: "status", header: "Outcome · verification", cell: (r) => <Status row={r} /> },
  { key: "latency", header: "Latency", align: "right", cell: (r) => <span className="whitespace-nowrap text-sm">{formatMs(r.total_ms)}</span> },
  {
    key: "usage",
    header: "Tokens · calls",
    align: "right",
    cell: (r) => (
      <div
        className="whitespace-nowrap text-sm tabular-nums"
        title={`${rowTokens(r) ?? "No model tokens"}\n${r.model_calls == null ? "Model calls not recorded" : `${r.model_calls} model calls`}, ${r.tool_calls} tool calls`}
      >
        <p>{r.tokens_in === 0 && r.tokens_out === 0 ? muted("—") : `${formatNumber(r.tokens_in)} / ${formatNumber(r.tokens_out)}`}</p>
        <p className="text-xs text-muted">
          {r.model_calls == null ? "—" : formatNumber(r.model_calls)} model · {formatNumber(r.tool_calls)} tool
        </p>
      </div>
    ),
  },
  { key: "cost", header: "Cost (est.)", align: "right", cell: (r) => <span className="whitespace-nowrap text-sm tabular-nums">{formatUsd(r.est_cost_usd)}</span> },
  {
    key: "evidence",
    header: "Cited / pack",
    align: "right",
    cell: (r) => (
      <span className="whitespace-nowrap text-sm" title={`${r.evidence_count} passages in the pack, ${r.cited_count} cited${r.result_count ? `, ${r.result_count} computed results` : ""}`}>
        {`${formatNumber(r.cited_count)} / ${formatNumber(r.evidence_count)}`}
      </span>
    ),
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
