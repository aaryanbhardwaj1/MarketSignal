import { humanize } from "@/lib/format";
import { isNonTerminalStatus, statusTone } from "@/lib/status";
import { StatusIndicator } from "./status-indicator";

/** @deprecated Use `<StatusIndicator>` with a label from `lib/labels`. Kept for older pages. */
export function StatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <StatusIndicator tone="neutral" label="No version" />;
  const label = humanize(status);
  return (
    <StatusIndicator
      tone={statusTone(status)}
      label={label.charAt(0).toUpperCase() + label.slice(1)}
      detail={isNonTerminalStatus(status) ? "in progress" : undefined}
    />
  );
}
