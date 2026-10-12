import type { TelemetryRunRow } from "@/lib/api/contracts";
import { Badge } from "@/components/ui/badge";
import { Table, type Column } from "@/components/ui/table";
import { formatDateTime, formatMs, formatNumber, formatUsd } from "@/lib/format";
import Link from "next/link";
import { routeReason, runStatus, terminationState, verificationDisposition } from "@/lib/labels";
import { flagLabel, outcomeFlags, rowTokens, shortId } from "@/lib/telemetry-view";

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
  const { implied, extra } = outcomeFlags(row.termination_state, row.flags);
  const outcomeTitle = [shown.code, ...implied.map((f) => `${flagLabel(f)} (${f})`)].join("\n");
  const [first, ...rest] = extra;
  return (
    <div className="flex flex-col items-start gap-0.5">
      <span className="flex flex-wrap items-center gap-1">
        <Badge tone={shown.tone ?? "neutral"} title={outcomeTitle}>
          {shown.known ? shown.label : shown.code}
        </Badge>
        {first && (
          <Badge tone="warn" title={first}>
            {flagLabel(first)}
          </Badge>
        )}
        {rest.length > 0 && (
          <Badge tone="neutral" title={rest.map((f) => `${flagLabel(f)} (${f})`).join("\n")}>
            <span aria-hidden>+{rest.length}</span>
            <span className="sr-only">{`${rest.length} more warnings: ${rest.map(flagLabel).join(", ")}`}</span>
          </Badge>
        )}
      </span>
      <span className="text-xs text-muted">
        {row.status !== "completed" && term && `Status: ${status.known ? status.label : row.status} · `}
        {disp ? `Verification: ${disp.label}` : "Verification not recorded"}
        {row.regenerated && " · regenerated"}
      </span>
    </div>
  );
}

const columns = (href: (row: TelemetryRunRow) => string): Column<TelemetryRunRow>[] => [
  {
    key: "time",
    header: "Run",
    width: "8.5rem",
    cell: (r) => (
      <div className="flex flex-col">
        <Link
          href={href(r)}
          aria-label={`Open run ${formatDateTime(r.created_at)} (${shortId(r.id)})`}
          className="whitespace-nowrap rounded-sm text-sm font-medium text-accent-text underline-offset-2 hover:underline"
        >
          {formatDateTime(r.created_at)}
        </Link>
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
  { key: "outcome", header: "Outcome", cell: (r) => <Outcome row={r} /> },
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

/** Runs list. Each row opens through a real link in the Run column (new tab and copy work). */
export function RunsTable({ rows, runHref }: { rows: TelemetryRunRow[]; runHref: (row: TelemetryRunRow) => string }) {
  return (
    <Table
      caption="Runs, newest first. Open a run from the Run column to see its telemetry."
      columns={columns(runHref)}
      rows={rows}
      rowKey={(r) => r.id}
      density="compact"
      empty="No runs match these filters."
    />
  );
}
