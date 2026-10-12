import { describeRoute } from "@/lib/run-mode";
import type { RunRoute } from "@/lib/run-stream";
import { Badge } from "../ui/badge";

/**
 * Which mode answered this run and why, worded exactly like the saved run's Research details.
 * Router reason codes and cues never appear here.
 */
export function RouteBadge({ route }: { route: RunRoute | null }) {
  const description = describeRoute(route);
  if (!description) return null;
  return (
    <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
      <Badge tone={description.tone}>{description.mode}</Badge>
      {description.reason && <span>{description.reason}</span>}
    </p>
  );
}
