"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { getEvidence } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type { EvidenceSource } from "@/lib/api/types";
import { evidenceViewerHref, handleAtVersion } from "@/lib/handles";

/**
 * Shown when the resolved version is not the latest. A link to the same locator at the
 * latest version is offered only after confirming that handle actually resolves; locators
 * can disappear or move between versions.
 */
export function VersionNotice({
  ws,
  handle,
  source,
}: {
  ws: string;
  handle: string;
  source: EvidenceSource;
}) {
  const latest = source.latest_version;
  const candidate = !source.is_latest && latest ? handleAtVersion(handle, latest) : null;
  const probe = useQuery({
    queryKey: queryKeys.evidence(ws, candidate ?? "", null),
    queryFn: ({ signal }) => getEvidence(ws, candidate as string, null, signal),
    enabled: candidate !== null,
    retry: false,
  });

  if (source.is_latest) return null;

  const label =
    source.version_status === "superseded"
      ? `superseded - latest is v${latest ?? "?"}`
      : `not the latest version - latest is v${latest ?? "?"}`;

  return (
    <div role="note" className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      <p className="font-medium">This evidence is v{source.version}, {label}.</p>
      <p className="mt-1 text-amber-900">
        The text below is exactly what was cited and remains immutable.{" "}
        {candidate && probe.isSuccess && (
          <Link href={evidenceViewerHref(ws, candidate)} className="font-medium underline">
            View the same locator at v{latest}
          </Link>
        )}
        {candidate && probe.isPending && <span>Checking whether v{latest} has the same locator...</span>}
        {candidate && probe.isError && (
          <span>The same locator does not resolve at v{latest}.</span>
        )}
      </p>
    </div>
  );
}
