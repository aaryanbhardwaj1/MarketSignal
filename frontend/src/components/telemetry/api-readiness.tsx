"use client";

import { useQuery } from "@tanstack/react-query";
import { StatusIndicator } from "@/components/ui/status-indicator";
import { apiGet } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

interface Readyz {
  status: "ready" | "degraded" | "not_ready";
  checks: Record<string, { status?: string }>;
}

const POLL_MS = 30_000;

/** Small "API ready" indicator from `GET /readyz` (503 means not ready; the body is not needed). */
export function ApiReadiness() {
  const q = useQuery({
    queryKey: ["readyz"],
    queryFn: ({ signal }) => apiGet<Readyz>("/readyz", { signal }),
    refetchInterval: POLL_MS,
    retry: false,
  });
  if (q.isPending) return <StatusIndicator tone="neutral" label="Checking API" />;
  if (q.isError) {
    const unreachable = !(q.error instanceof ApiError) || q.error.status === 0;
    return (
      <span title={unreachable ? "GET /readyz did not respond" : `GET /readyz returned ${q.error instanceof ApiError ? q.error.status : "an error"}: a required check is failing`}>
        <StatusIndicator tone="danger" label={unreachable ? "API unreachable" : "API not ready"} />
      </span>
    );
  }
  const failing = Object.entries(q.data.checks ?? {})
    .filter(([, c]) => c.status && c.status !== "ok")
    .map(([name]) => name);
  if (q.data.status === "ready") return <StatusIndicator tone="success" label="API ready" />;
  return (
    <span title={failing.length ? `Checks not passing: ${failing.join(", ")}` : undefined}>
      <StatusIndicator tone={q.data.status === "degraded" ? "warn" : "danger"} label={q.data.status === "degraded" ? "API degraded" : "API not ready"} />
    </span>
  );
}
