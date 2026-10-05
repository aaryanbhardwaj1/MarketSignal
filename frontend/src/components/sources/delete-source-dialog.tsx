"use client";

import type { SourceSummary } from "@/lib/api/types";
import { ConfirmDialog } from "../ui/confirm-dialog";
import { InlineError } from "../ui/error-panel";

export function DeleteSourceDialog({
  source,
  busy,
  error,
  onConfirm,
  onCancel,
}: {
  source: Pick<SourceSummary, "source_code" | "title"> | null;
  busy: boolean;
  error: unknown;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <ConfirmDialog
      open={source !== null}
      title={`Delete ${source?.source_code ?? "source"}?`}
      confirmLabel="Delete and purge"
      busy={busy}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <p>
        <span className="font-medium text-slate-900">{source?.title}</span> and all of its versions
        will be purged from retrieval. Existing evidence handles will resolve to a deletion
        tombstone. This cannot be undone.
      </p>
      {error ? (
        <div className="mt-3">
          <InlineError error={error} />
        </div>
      ) : null}
    </ConfirmDialog>
  );
}
