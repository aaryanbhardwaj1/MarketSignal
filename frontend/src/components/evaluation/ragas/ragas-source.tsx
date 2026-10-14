"use client";

import { Popover } from "@/components/ui/popover";

/** "Source" trigger opening the stored artifact path and JSON pointer (or report anchor). */
export function RagasSource({ path, locator }: { path: string; locator: string }) {
  return (
    <Popover
      label="Metric source"
      panelClassName="w-80"
      trigger={
        <button
          type="button"
          aria-label={`Source: ${path} ${locator}`}
          className="rounded-sm text-xs text-accent-text underline decoration-dotted underline-offset-2"
        >
          Source
        </button>
      }
    >
      <dl className="flex flex-col gap-2 p-3 text-xs">
        <div>
          <dt className="text-muted">Artifact</dt>
          <dd className="mt-0.5 break-all font-mono text-primary">{path}</dd>
        </div>
        <div>
          <dt className="text-muted">Location</dt>
          <dd className="mt-0.5 break-all font-mono text-primary">{locator}</dd>
        </div>
      </dl>
    </Popover>
  );
}
