import { Suspense } from "react";
import { LibraryView } from "@/components/library/library-view";

/** `?ev=` (and the legacy `?h=`) with `&child=` open the evidence drawer from the workspace layout. */
export default async function EvidenceLibraryPage({ params }: PageProps<"/w/[ws]/evidence">) {
  const { ws } = await params;
  return (
    <Suspense>
      <LibraryView ws={ws} />
    </Suspense>
  );
}
