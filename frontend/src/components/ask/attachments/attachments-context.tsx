"use client";

import { useQueries, useQueryClient, type Query } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { getSource, uploadSource } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/query-keys";
import type { SourceDetail, SourceVersion } from "@/lib/api/types";
import {
  attachmentKind,
  attachmentStatus,
  isSettled,
  processingFailureMessage,
  uploadErrorMessage,
  validateAttachment,
  type AttachmentKind,
  type AttachmentStatus,
} from "@/lib/attachments";

/** Attached files are workspace evidence; chat uploads are filed as internal material. */
const ATTACHMENT_SOURCE_CLASS = "internal" as const;
const POLL_FAST_MS = 1_500;
const POLL_SLOW_MS = 5_000;
const FAST_POLL_WINDOW_MS = 20_000;

interface AttachmentRecord {
  id: string;
  name: string;
  size: number;
  kind: AttachmentKind;
  /** Upload request state; after "accepted" the server's processing status takes over. */
  phase: "uploading" | "accepted" | "rejected";
  error: string | null;
  sourceId: string | null;
  versionId: string | null;
  acceptedAt: number;
  /** The same bytes were already in the workspace: the existing version is tracked instead. */
  duplicate: boolean;
}

export interface AttachmentView {
  id: string;
  name: string;
  size: number;
  kind: AttachmentKind;
  status: AttachmentStatus;
  /** Why it failed, in plain words (null unless failed). */
  reason: string | null;
  duplicate: boolean;
}

export interface Attachments {
  items: AttachmentView[];
  add: (files: Iterable<File>) => void;
  remove: (id: string) => void;
  /** Removes every chip (New chat). Uploads already accepted keep processing on the server. */
  clear: () => void;
  /** Removes ready and failed chips (after a question is sent); in-flight ones stay visible. */
  clearSettled: () => void;
}

const AttachmentsContext = createContext<Attachments | null>(null);

export function useAttachments(): Attachments {
  const value = useContext(AttachmentsContext);
  if (!value) throw new Error("useAttachments must be used inside AttachmentsProvider");
  return value;
}

function trackedVersion(detail: SourceDetail | undefined, versionId: string | null): SourceVersion | undefined {
  if (!detail) return undefined;
  return detail.versions.find((v) => v.version_id === versionId) ?? detail.versions[0];
}

/** Derives the chip state from the local record and the latest polled source detail. */
export function toView(record: AttachmentRecord, detail: SourceDetail | undefined, polledAt: number): AttachmentView {
  const base = { id: record.id, name: record.name, size: record.size, kind: record.kind, duplicate: record.duplicate };
  if (record.phase === "uploading") return { ...base, status: "uploading", reason: null };
  if (record.phase === "rejected") return { ...base, status: "failed", reason: record.error ?? "Upload failed" };
  const version = trackedVersion(detail, record.versionId);
  if (!version) return { ...base, status: "processing", reason: null };
  const status = attachmentStatus(version.status, Math.max(0, polledAt - record.acceptedAt));
  const reason = status === "failed" ? processingFailureMessage(version.error_code) : null;
  return { ...base, status, reason };
}

function pollInterval(acceptedAt: number) {
  return (query: Query<SourceDetail>) => {
    const data = query.state.data;
    const version = data?.versions[0];
    if (version && isSettled(attachmentStatus(version.status, 0))) return false;
    return query.state.dataUpdatedAt - acceptedAt < FAST_POLL_WINDOW_MS ? POLL_FAST_MS : POLL_SLOW_MS;
  };
}

/** Holds the composer's attachments across navigation (mounted with the Ask session). */
export function AttachmentsProvider({ ws, children }: { ws: string; children: ReactNode }) {
  const queryClient = useQueryClient();
  const [records, setRecords] = useState<AttachmentRecord[]>([]);
  const nextId = useRef(0);
  const uploads = useRef(new Map<string, AbortController>());

  const update = useCallback((id: string, patch: Partial<AttachmentRecord>) => {
    setRecords((rows) => rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  }, []);

  const startUpload = useCallback(
    async (id: string, file: File) => {
      const controller = new AbortController();
      uploads.current.set(id, controller);
      try {
        const result = await uploadSource(
          ws,
          { file, filename: file.name, source_class: ATTACHMENT_SOURCE_CLASS },
          controller.signal,
        );
        update(id, {
          phase: "accepted",
          sourceId: result.source_id,
          versionId: result.version_id,
          acceptedAt: Date.now(),
          duplicate: !result.created,
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        update(id, { phase: "rejected", error: uploadErrorMessage(error) });
      } finally {
        uploads.current.delete(id);
      }
    },
    [ws, update],
  );

  const add = useCallback(
    (files: Iterable<File>) => {
      const added: AttachmentRecord[] = [];
      const toUpload: [string, File][] = [];
      for (const file of files) {
        nextId.current += 1;
        const id = `attachment-${nextId.current}`;
        const check = validateAttachment(file);
        added.push({
          id,
          name: file.name,
          size: file.size,
          kind: attachmentKind(file.name),
          phase: check.ok ? "uploading" : "rejected",
          error: check.ok ? null : check.reason,
          sourceId: null,
          versionId: null,
          acceptedAt: 0,
          duplicate: false,
        });
        if (check.ok) toUpload.push([id, file]);
      }
      if (added.length === 0) return;
      setRecords((rows) => [...rows, ...added]);
      for (const [id, file] of toUpload) void startUpload(id, file);
    },
    [startUpload],
  );

  const remove = useCallback((id: string) => {
    uploads.current.get(id)?.abort();
    setRecords((rows) => rows.filter((r) => r.id !== id));
  }, []);

  const clear = useCallback(() => {
    for (const controller of uploads.current.values()) controller.abort();
    setRecords([]);
  }, []);

  const tracked = records.filter((r) => r.phase === "accepted" && r.sourceId !== null);
  const polls = useQueries({
    queries: tracked.map((r) => ({
      queryKey: queryKeys.source(ws, r.sourceId ?? ""),
      queryFn: ({ signal }: { signal: AbortSignal }) => getSource(ws, r.sourceId ?? "", signal),
      refetchInterval: pollInterval(r.acceptedAt),
      retry: 1,
    })),
  });

  const items = records.map((record) => {
    const index = tracked.indexOf(record);
    const poll = index >= 0 ? polls[index] : undefined;
    return toView(record, poll?.data, poll?.dataUpdatedAt ?? record.acceptedAt);
  });

  const readyCount = items.filter((i) => i.status === "ready").length;
  useEffect(() => {
    if (readyCount > 0) void queryClient.invalidateQueries({ queryKey: queryKeys.sources(ws) });
  }, [readyCount, queryClient, ws]);

  const settledIds = items.filter((i) => isSettled(i.status)).map((i) => i.id).join(",");
  const clearSettled = useCallback(() => {
    const settled = new Set(settledIds.split(","));
    setRecords((rows) => rows.filter((r) => !settled.has(r.id)));
  }, [settledIds]);

  // `items` is derived on every render (it reads the polled queries), so the value is too.
  const value: Attachments = { items, add, remove, clear, clearSettled };
  return <AttachmentsContext.Provider value={value}>{children}</AttachmentsContext.Provider>;
}
