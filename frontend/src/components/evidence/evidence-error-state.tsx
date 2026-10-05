import type { ReactNode } from "react";
import type { Tombstone } from "@/lib/api/types";
import { describeError, isApiError } from "@/lib/api/errors";
import { formatDateTime } from "@/lib/format";
import { ErrorPanel } from "../ui/error-panel";

function readTombstone(error: unknown): Tombstone | null {
  if (!isApiError(error)) return null;
  const t = error.details.tombstone;
  return t && typeof t === "object" ? (t as Tombstone) : null;
}

function Panel({
  tone,
  title,
  code,
  children,
}: {
  tone: "amber" | "slate" | "red";
  title: string;
  code: string;
  children: ReactNode;
}) {
  const tones = {
    amber: "border-amber-300 bg-amber-50 text-amber-950",
    slate: "border-slate-300 bg-slate-50 text-slate-900",
    red: "border-red-300 bg-red-50 text-red-950",
  };
  return (
    <div role="alert" className={`rounded-xl border-2 border-dashed p-6 ${tones[tone]}`}>
      <p className="font-mono text-xs font-semibold tracking-wide opacity-70">{code}</p>
      <h2 className="mt-1 text-lg font-semibold">{title}</h2>
      <div className="mt-2 text-sm">{children}</div>
    </div>
  );
}

export function EvidenceErrorState({ error, handle }: { error: unknown; handle: string }) {
  const { code, message } = describeError(error);
  const status = isApiError(error) ? error.status : 0;

  if (code === "MALFORMED_HANDLE" || status === 400) {
    return (
      <Panel tone="amber" code={`400 ${code}`} title="Malformed handle">
        <p>
          <code className="font-mono">{handle}</code> is not a canonical evidence handle. Expected{" "}
          <code className="font-mono">WORKSPACE/SOURCE-CODE@vN:LOCATOR</code>, e.g.{" "}
          <code className="font-mono">NORTHSTAR/SURVEY-2026@v1:R185</code>.
        </p>
        <p className="mt-1 opacity-80">{message}</p>
      </Panel>
    );
  }

  if (code === "SOURCE_DELETED" || status === 410) {
    const t = readTombstone(error);
    return (
      <Panel tone="red" code={`410 ${code}`} title="Source deleted - evidence tombstone">
        <p>The source behind this handle was deleted and its text purged. Only the tombstone remains.</p>
        {t && (
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
            <dt className="font-medium">Handle</dt>
            <dd className="break-all font-mono">{t.handle}</dd>
            <dt className="font-medium">Source</dt>
            <dd>
              <span className="font-mono">{t.source_code}</span> - {t.title}
            </dd>
            <dt className="font-medium">Version</dt>
            <dd>v{t.version}</dd>
            <dt className="font-medium">Deleted</dt>
            <dd>{formatDateTime(t.deleted_at)}</dd>
          </dl>
        )}
      </Panel>
    );
  }

  if (code === "EVIDENCE_NOT_FOUND" || status === 404) {
    return (
      <Panel tone="slate" code={`404 ${code}`} title="Evidence not found">
        <p>
          No evidence for <code className="break-all font-mono">{handle}</code> in this workspace.
          Check the workspace prefix, source code, version and locator.
        </p>
        <p className="mt-1 opacity-80">{message}</p>
      </Panel>
    );
  }

  return <ErrorPanel error={error} title="Could not resolve evidence" />;
}
