"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { getEvidence } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import { evidenceViewerHref, isUuid } from "@/lib/handles";
import { resolveActiveSpan } from "@/lib/highlight";
import { PageHeader } from "../ui/card";
import { Loading } from "../ui/loading";
import { EvidenceDetail } from "./evidence-detail";
import { EvidenceErrorState } from "./evidence-error-state";
import { EvidenceLookupForm } from "./evidence-lookup-form";

export function EvidenceView({
  ws,
  handle,
  child,
}: {
  ws: string;
  handle: string;
  child: string | null;
}) {
  const router = useRouter();
  // The API rejects non-UUID child ids with a non-envelope 422; drop them client-side.
  const childId = child && isUuid(child) ? child : null;
  const invalidChild = child !== null && childId === null;

  const query = useQuery({
    queryKey: queryKeys.evidence(ws, handle, childId),
    queryFn: ({ signal }) => getEvidence(ws, handle, childId, signal),
    enabled: handle.length > 0,
    placeholderData: (prev, prevQuery) =>
      prevQuery?.queryKey[3] === handle ? keepPreviousData(prev) : undefined,
  });

  const selectChild = (id: string | null) => {
    router.replace(evidenceViewerHref(ws, handle, id), { scroll: false });
  };

  return (
    <>
      <PageHeader
        eyebrow={ws}
        title="Evidence viewer"
        description="Resolve an immutable evidence handle to the exact parent text, the cited child span and its provenance."
      />
      <EvidenceLookupForm key={handle} ws={ws} initialHandle={handle} />
      {invalidChild && (
        <p role="alert" className="text-sm text-amber-700">
          Ignored child parameter <code className="font-mono">{child}</code>: not a valid UUID.
        </p>
      )}
      {!handle ? (
        <p className="text-sm text-slate-500">
          Enter a handle above, or open one from the smoke search results.
        </p>
      ) : query.isPending ? (
        <Loading label="Resolving evidence..." />
      ) : query.isError ? (
        <EvidenceErrorState error={query.error} handle={handle} />
      ) : (
        <>
          {childId && !query.data.children.some((c) => c.child_id === childId) && (
            <p role="alert" className="text-sm text-amber-700">
              Child <code className="font-mono">{childId}</code> is not a span of this parent; no
              highlight shown.
            </p>
          )}
          <EvidenceDetail
          ws={ws}
          evidence={query.data}
          span={resolveActiveSpan(query.data, childId)}
          onSelectChild={selectChild}
          />
        </>
      )}
    </>
  );
}
