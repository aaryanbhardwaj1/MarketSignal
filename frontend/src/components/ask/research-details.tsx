import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Disclosure, DevDetails } from "@/components/ui/disclosure";
import { KeyValueList } from "@/components/ui/key-value";
import { formatMs } from "@/lib/format";
import type { SavedRunView } from "@/lib/saved-run";
import { telemetryRunHref } from "./ask-routes";

function Summary({ view }: { view: SavedRunView }) {
  const parts = [view.mode, view.durationMs !== null ? formatMs(view.durationMs) : null, view.verification?.summary];
  return (
    <span className="flex min-w-0 flex-wrap items-baseline gap-x-2">
      Research details
      <span className="text-sm font-normal text-muted">{parts.filter(Boolean).join(" · ")}</span>
    </span>
  );
}

/** Plain-language account of how an answer was produced. Codes and ids sit in Technical details. */
export function ResearchDetails({ ws, view }: { ws: string; view: SavedRunView }) {
  const items = [
    { label: "Mode used", value: view.mode },
    ...(view.modeReason ? [{ label: "How the mode was chosen", value: view.modeReason }] : []),
    ...(view.durationMs !== null ? [{ label: "Duration", value: formatMs(view.durationMs) }] : []),
    ...(view.verification
      ? [
          {
            label: "Citation checks",
            value: (
              <span className="flex flex-wrap items-center gap-2">
                <Badge tone={view.verification.tone}>{view.verification.label}</Badge>
                <span className="text-sm text-muted">{view.verification.summary}</span>
              </span>
            ),
          },
        ]
      : []),
  ];
  return (
    <Disclosure summary={<Summary view={view} />}>
      <div className="flex flex-col gap-4">
        <KeyValueList items={items} columns={2} />
        {view.steps.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-primary">Research steps</h4>
            <ol className="mt-1.5 flex flex-col gap-1 text-sm text-secondary">
              {view.steps.map((step, i) => (
                <li key={step.key} className="flex gap-2">
                  <span className="w-5 shrink-0 text-right tabular-nums text-muted">{i + 1}.</span>
                  <span className="min-w-0">
                    {step.label}
                    {step.detail && <span className="text-muted"> · {step.detail}</span>}
                    {step.failed && <span className="text-warn"> · Did not complete</span>}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}
        {view.notices.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-primary">Notices</h4>
            <ul className="mt-1.5 flex flex-col gap-1 text-sm text-secondary">
              {view.notices.map((notice) => (
                <li key={notice.label}>
                  {notice.label}
                  {notice.description && <span className="text-muted">. {notice.description}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="border-t border-border pt-3">
          <DevDetails data={view.technical}>
            <Link
              href={telemetryRunHref(ws, view.technical.runId)}
              className="rounded-sm font-sans text-sm font-medium text-accent-text hover:underline"
            >
              Open this run in Telemetry (Developer tools)
            </Link>
          </DevDetails>
        </div>
      </div>
    </Disclosure>
  );
}
