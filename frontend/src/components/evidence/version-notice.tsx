"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { getEvidence } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type { EvidenceSource } from "@/lib/api/types";
import { evidenceViewerHref, handleAtVersion } from "@/lib/handles";
import { Callout } from "../ui/callout";
import { useOptionalEvidenceDrawer } from "./drawer-context";

/**
 * Shown when the cited version is not the latest. A link to the same passage in the latest
 * version is offered only after confirming it resolves; locators can move between versions.
 */
export function VersionNotice({ ws, handle, source }: { ws: string; handle: string; source: EvidenceSource }) {
  const drawer = useOptionalEvidenceDrawer();
  const latest = source.latest_version;
  const candidate = !source.is_latest && latest ? handleAtVersion(handle, latest) : null;
  const probe = useQuery({
    queryKey: queryKeys.evidence(ws, candidate ?? "", null),
    queryFn: ({ signal }) => getEvidence(ws, candidate as string, null, signal),
    enabled: candidate !== null,
    retry: false,
  });

  if (source.is_latest) return null;

  const title =
    source.version_status === "superseded"
      ? `Superseded: this passage is from version ${source.version}${latest ? `; version ${latest} is current` : ""}`
      : `This passage is from version ${source.version}${latest ? `; version ${latest} is the latest` : ""}`;

  return (
    <Callout tone="warn" title={title}>
      The text below is exactly what was cited.{" "}
      {candidate && probe.isSuccess && (
        <Link
          href={evidenceViewerHref(ws, candidate)}
          onClick={(event) => {
            if (!drawer) return;
            event.preventDefault();
            drawer.openEvidence({ handle: candidate });
          }}
          className="font-medium text-accent-text underline"
        >
          View the same passage in version {latest}
        </Link>
      )}
      {candidate && probe.isPending && <span>Checking the latest version...</span>}
      {candidate && probe.isError && <span>This passage is not in version {latest}.</span>}
    </Callout>
  );
}
