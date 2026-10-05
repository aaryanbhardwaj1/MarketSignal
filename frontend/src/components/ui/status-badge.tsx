import { humanize } from "@/lib/format";
import { isNonTerminalStatus, statusTone } from "@/lib/status";
import { Badge } from "./badge";

export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <Badge tone="muted">no version</Badge>;
  const inFlight = isNonTerminalStatus(status);
  return (
    <Badge tone={statusTone(status)} title={inFlight ? "In progress" : undefined}>
      {inFlight && (
        <span aria-hidden className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
      )}
      {humanize(status)}
    </Badge>
  );
}
