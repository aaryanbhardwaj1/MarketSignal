"use client";

import { Check, CircleAlert, Clock, File, FileSpreadsheet, FileText, LoaderCircle, Presentation, X, type LucideIcon } from "lucide-react";
import { cx } from "@/lib/cx";
import { formatBytes } from "@/lib/format";
import { attachmentStatusLabel, clipFileName, type AttachmentKind, type AttachmentStatus } from "@/lib/attachments";
import type { AttachmentView } from "./attachments-context";

const KIND_ICON: Readonly<Record<AttachmentKind, LucideIcon>> = {
  pdf: FileText,
  document: FileText,
  presentation: Presentation,
  spreadsheet: FileSpreadsheet,
  text: FileText,
  other: File,
};

const STATUS_TONE: Readonly<Record<AttachmentStatus, string>> = {
  uploading: "text-muted",
  processing: "text-muted",
  queued: "text-muted",
  ready: "text-success",
  failed: "text-danger",
};

function StatusIcon({ status }: { status: AttachmentStatus }) {
  const cls = "size-3 shrink-0";
  if (status === "ready") return <Check aria-hidden className={cls} />;
  if (status === "failed") return <CircleAlert aria-hidden className={cls} />;
  if (status === "queued") return <Clock aria-hidden className={cls} />;
  return <LoaderCircle aria-hidden className={cx(cls, "motion-safe:animate-spin")} />;
}

/** Status text for a chip: failures carry their reason, duplicates say they were already there. */
export function chipStatusText(item: AttachmentView): string {
  if (item.status === "failed") return item.reason ?? attachmentStatusLabel("failed");
  if (item.status === "ready" && item.duplicate) return "Already in workspace";
  return attachmentStatusLabel(item.status);
}

function AttachmentChip({ item, onRemove }: { item: AttachmentView; onRemove: (id: string) => void }) {
  const Icon = KIND_ICON[item.kind];
  const status = chipStatusText(item);
  return (
    <li
      className={cx(
        "ms-pop-in flex max-w-full items-center gap-2 rounded-md border bg-surface py-1 pl-2 pr-1 text-sm",
        item.status === "failed" ? "border-danger/40" : "border-border",
      )}
    >
      <Icon aria-hidden className="size-4 shrink-0 text-secondary" />
      <span className="flex min-w-0 flex-col leading-tight">
        <span className="truncate font-medium text-primary" title={item.name}>
          {clipFileName(item.name)}
        </span>
        <span className={cx("flex items-center gap-1 text-xs", STATUS_TONE[item.status])}>
          <StatusIcon status={item.status} />
          <span>{status}</span>
          <span aria-hidden className="text-muted">
            · <span className="tabular-nums">{formatBytes(item.size)}</span>
          </span>
        </span>
      </span>
      <button
        type="button"
        onClick={() => onRemove(item.id)}
        aria-label={`Remove ${item.name}`}
        className="ml-1 inline-flex size-6 shrink-0 items-center justify-center rounded-sm text-muted hover:bg-surface-muted hover:text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
      >
        <X aria-hidden className="size-3.5" />
      </button>
    </li>
  );
}

/** Compact, removable chips for the composer's attached files, with live upload status. */
export function AttachmentChips({ items, onRemove }: { items: readonly AttachmentView[]; onRemove: (id: string) => void }) {
  if (items.length === 0) return null;
  return (
    <ul aria-label="Attached files" aria-live="polite" className="flex flex-wrap gap-2 px-3 pt-3">
      {items.map((item) => (
        <AttachmentChip key={item.id} item={item} onRemove={onRemove} />
      ))}
    </ul>
  );
}
