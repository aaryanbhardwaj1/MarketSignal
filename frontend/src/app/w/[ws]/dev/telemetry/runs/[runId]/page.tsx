import { RunDetail } from "@/components/telemetry/run-detail";

export default async function TelemetryRunPage({ params }: PageProps<"/w/[ws]/dev/telemetry/runs/[runId]">) {
  const { ws, runId } = await params;
  return <RunDetail ws={ws} runId={runId} />;
}
