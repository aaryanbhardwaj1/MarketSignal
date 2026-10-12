import type { Metadata } from "next";
import { RunDetail } from "@/components/telemetry/run-detail";

export async function generateMetadata({ params }: PageProps<"/w/[ws]/dev/telemetry/runs/[runId]">): Promise<Metadata> {
  const { runId } = await params;
  return { title: `Run telemetry ${runId.slice(0, 8)} · Telemetry` };
}

export default async function TelemetryRunPage({ params }: PageProps<"/w/[ws]/dev/telemetry/runs/[runId]">) {
  const { ws, runId } = await params;
  return <RunDetail ws={ws} runId={runId} />;
}
