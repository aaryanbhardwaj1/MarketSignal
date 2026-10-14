"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { DevDetails } from "@/components/ui/disclosure";
import { KeyValueList } from "@/components/ui/key-value";
import type { SavedRunView } from "@/lib/saved-run";
import { telemetryRunHref } from "@/lib/routes";
import { SavedResearchSteps } from "./research-timeline";

const SUBHEAD = "text-xs font-medium uppercase tracking-wide text-muted";

/**
 * How a saved answer was produced: "Research steps" (collapsed summary with durations, observable
 * stages with Replay), then the individual searches and calculations, how the mode was chosen,
 * citation checks and notices. Codes and ids sit only in Technical details.
 */
export function ResearchDetails({ ws, view }: { ws: string; view: SavedRunView }) {
  const items = [
    ...(view.modeReason ? [{ label: "How the mode was chosen", value: view.modeReason }] : []),
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
    <SavedResearchSteps summary={view.stages}>
      {view.steps.length > 0 && (
        <div>
          <h4 className={SUBHEAD}>Searches and calculations</h4>
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
      {items.length > 0 && <KeyValueList items={items} columns={1} />}
      {view.notices.length > 0 && (
        <div>
          <h4 className={SUBHEAD}>Notices</h4>
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
      <DevDetails data={view.technical}>
        <Link
          href={telemetryRunHref(ws, view.technical.runId)}
          className="rounded-sm font-sans text-sm font-medium text-accent-text hover:underline"
        >
          Open this run in Telemetry (Developer tools)
        </Link>
      </DevDetails>
    </SavedResearchSteps>
  );
}
