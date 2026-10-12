import type { TelemetryRunRow } from "@/lib/api/contracts";
import { Badge } from "@/components/ui/badge";
import { Table, type Column } from "@/components/ui/table";
import { formatDateTime, formatMs, formatNumber, formatUsd } from "@/lib/format";
import { degradationFlag, routeReason, runStatus, terminationState, verificationDisposition } from "@/lib/labels";
import { rowTokens, shortId } from "@/lib/telemetry-view";

function routeText(code: string | null): string {
  if (!code) return "Route not recorded";
  const h = routeReason(code);
  return h.known ? h.label : code;
}

const muted = (text: string) => <span className="text-muted">{text}</span>;

function Outcome({ row }: { row: TelemetryRunRow }) {
  const term = row.termination_state ? terminationState(row.termination_state) : null;
  const status = runStatus(row.status);
  const shown = term ?? status;
  const disp = row.verification_disposition ? verificationDisposition(row.verification_disposition) : null;
  return (
    <div className="flex flex-col items-start gap-1">
      <Badge tone={shown.tone ?? "neutral"} title={shown.code}>
        {shown.known ? shown.label : shown.code}
      </Badge>
      {row.status !== "completed" && term && <span className="text-xs text-muted">Status: {status.known ? status.label : row.status}</span>}
      <span className="text-xs text-muted">
        {disp ? `Verification: ${disp.label}` : "Verification not recorded"}
        {row.regenerated && " · regenerated"}
      </span>
      <Warnings flags={row.flags} />
    </div>
  );
}

function Warnings({ flags }: { flags: string[] }) {
  if (flags.length === 0) return null;
  return (
    <ul aria-label="Warnings" className="flex max-w-64 flex-wrap gap-1">
      {flags.map((f) => {
        const h = degradationFlag(f);
        return (
          <li key={f}>
            <Badge tone="warn" title={f}>
              {h.known ? h.label : f}
            </Badge>
          </li>
        );
      })}
    </ul>
  );
}

const COLUMNS: Column<TelemetryRunRow>[] = [
  {
    key: "time",
    header: "Run",
    width: "8.5rem",
    cell: (r) => (
      <div className="flex flex-col">
        <span className="whitespace-nowrap text-sm">{formatDateTime(r.created_at)}</span>
        <span className="font-mono text-xs text-muted" title={r.id}>
          {shortId(r.id)}
        </span>
      </div>
    ),
  },
  {
    key: "question",
    header: "Question, mode and route",
    cell: (r) => (
      <div className="min-w-48">
        <p className="line-clamp-2 text-sm" title={r.question}>
          {r.question}
        </p>
        <p className="mt-0.5 text-xs text-muted">
          <span className="font-medium capitalize text-secondary">{r.mode}</span> · {routeText(r.route_reason)}
        </p>
      </div>
    ),
  },
  { key: "outcome", header: "Outcome and warnings", cell: (r) => <Outcome row={r} /> },
  { key: "latency", header: "Latency", align: "right", cell: (r) => <span className="whitespace-nowrap text-sm">{formatMs(r.total_ms)}</span> },
  {
    key: "calls",
    header: (
      <span>
        Calls<span className="block text-xs font-normal text-muted">model / tool</span>
      </span>
    ),
    align: "right",
    cell: (r) => (
      <span className="whitespace-nowrap text-sm" title="Model calls / tool calls">
        {r.model_calls == null ? "n/a" : formatNumber(r.model_calls)} / {formatNumber(r.tool_calls)}
      </span>
    ),
  },
  {
    key: "tokens",
    header: "Tokens and est. cost",
    align: "right",
    cell: (r) => (
      <span className="whitespace-nowrap text-sm" title={rowTokens(r) ?? "No model tokens"}>
        {r.tokens_in === 0 && r.tokens_out === 0 ? muted("No tokens") : `${formatNumber(r.tokens_in)} / ${formatNumber(r.tokens_out)}`}
        <span className="block text-xs text-muted">{`${formatUsd(r.est_cost_usd)} est.`}</span>
      </span>
    ),
  },
  {
    key: "evidence",
    header: "Evidence cited",
    align: "right",
    cell: (r) => (
      <span className="whitespace-nowrap text-sm" title={`${r.evidence_count} passages in the pack, ${r.cited_count} cited`}>
        {`${formatNumber(r.cited_count)} of ${formatNumber(r.evidence_count)}`}
        <span className="block text-xs text-muted">cited</span>
        {r.result_count > 0 && <span className="block text-xs text-muted">{formatNumber(r.result_count)} computed</span>}
      </span>
    ),
  },
];

export function RunsTable({ rows, onOpen }: { rows: TelemetryRunRow[]; onOpen: (row: TelemetryRunRow) => void }) {
  return (
    <Table
      caption="Runs, newest first. Select a row to open its telemetry."
      columns={COLUMNS}
      rows={rows}
      rowKey={(r) => r.id}
      onRowClick={onOpen}
      density="compact"
      empty="No runs match these filters."
    />
  );
}
