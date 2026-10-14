/**
 * Chat composer attachments: pure helpers. Attached files are uploaded to the workspace's
 * evidence (`POST /sources`) and become searchable once processed. These checks mirror the
 * server's upload validation for early feedback only; the server stays the authority.
 */
import { isApiError, NETWORK_ERROR } from "./api/errors";
import type { VersionStatus } from "./api/types";

/** Extensions accepted by the server's upload validation (`ingestion/validation.py`). */
export const ATTACHMENT_EXTENSIONS = [".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".md", ".markdown", ".txt"] as const;
/** `accept` attribute for the file picker. */
export const ATTACHMENT_ACCEPT = ATTACHMENT_EXTENSIONS.join(",");
/** Mirrors the server default `upload_max_bytes` (25 MB). */
export const ATTACHMENT_MAX_BYTES = 25 * 1024 * 1024;
/** A file still queued after this long is shown as "Queued for processing" (no worker running). */
export const QUEUED_NOTICE_AFTER_MS = 8_000;

const TOO_LARGE = "File too large (max 25 MB)";
const UNSUPPORTED = "Unsupported file type";

export type AttachmentKind = "pdf" | "document" | "presentation" | "spreadsheet" | "text" | "other";
/** Chip status: the upload request, then the server's processing of the stored version. */
export type AttachmentStatus = "uploading" | "processing" | "queued" | "ready" | "failed";

export type AttachmentCheck = { ok: true } | { ok: false; reason: string };

export function fileExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot).toLowerCase() : "";
}

/** Client-side pre-check of a picked file (type, emptiness, size). */
export function validateAttachment(file: { name: string; size: number }): AttachmentCheck {
  if (!(ATTACHMENT_EXTENSIONS as readonly string[]).includes(fileExtension(file.name))) {
    return { ok: false, reason: UNSUPPORTED };
  }
  if (file.size <= 0) return { ok: false, reason: "Empty file" };
  if (file.size > ATTACHMENT_MAX_BYTES) return { ok: false, reason: TOO_LARGE };
  return { ok: true };
}

const KIND_BY_EXTENSION: Readonly<Record<string, AttachmentKind>> = {
  ".pdf": "pdf",
  ".docx": "document",
  ".pptx": "presentation",
  ".xlsx": "spreadsheet",
  ".csv": "spreadsheet",
  ".md": "text",
  ".markdown": "text",
  ".txt": "text",
};

export function attachmentKind(name: string): AttachmentKind {
  return KIND_BY_EXTENSION[fileExtension(name)] ?? "other";
}

/** Shortens a long file name in the middle, keeping its start and extension visible. */
export function clipFileName(name: string, max = 28): string {
  if (name.length <= max) return name;
  const ext = fileExtension(name);
  const tail = ext && ext.length < max / 2 ? ext : "";
  const head = name.slice(0, max - tail.length - 1);
  return `${head}…${tail}`;
}

/** Chip status for a stored version; `elapsedMs` is the time since the upload was accepted. */
export function attachmentStatus(status: VersionStatus, elapsedMs: number): AttachmentStatus {
  switch (status) {
    case "ready":
    case "ready_degraded":
    case "superseded":
      return "ready";
    case "failed":
    case "purged":
      return "failed";
    case "queued":
      return elapsedMs >= QUEUED_NOTICE_AFTER_MS ? "queued" : "processing";
    default:
      return "processing";
  }
}

const STATUS_LABEL: Readonly<Record<AttachmentStatus, string>> = {
  uploading: "Uploading",
  processing: "Processing",
  queued: "Queued for processing",
  ready: "Ready",
  failed: "Failed",
};

export function attachmentStatusLabel(status: AttachmentStatus): string {
  return STATUS_LABEL[status];
}

/** Ready or failed: nothing more will happen to this attachment. */
export function isSettled(status: AttachmentStatus): boolean {
  return status === "ready" || status === "failed";
}

const UPLOAD_ERRORS: Readonly<Record<string, string>> = {
  UNSUPPORTED_TYPE: UNSUPPORTED,
  FILE_TOO_LARGE: TOO_LARGE,
  CONTENT_TOO_LARGE: "File content is too large",
  ENCRYPTED_DOCUMENT: "Encrypted or password-protected file",
  EMPTY_DOCUMENT: "Empty file",
  PARSE_FAILED: "The file could not be read",
  SOURCE_TYPE_MISMATCH: "Conflicts with an existing source",
  [NETWORK_ERROR]: "Cannot reach the server",
};

/** Plain message for a rejected upload request (never a raw code). */
export function uploadErrorMessage(error: unknown): string {
  if (isApiError(error)) return UPLOAD_ERRORS[error.code] ?? "Upload failed";
  return "Upload failed";
}

const PROCESSING_ERRORS: Readonly<Record<string, string>> = {
  PARSE_FAILED: "The file could not be read",
  PARSE_TIMEOUT: "The file took too long to read",
  ENCRYPTED_DOCUMENT: "Encrypted or password-protected file",
  EMPTY_DOCUMENT: "No readable text in the file",
  MALFORMED_SPREADSHEET: "The spreadsheet could not be read",
  CONTENT_TOO_LARGE: "File content is too large",
  EMBEDDER_UNAVAILABLE: "Search indexing is unavailable",
  DB_UNAVAILABLE: "Storage is unavailable",
  HEALTH_CHECK_FAILED: "Processing checks did not pass",
  SOURCE_DELETED: "Removed from the workspace",
};

/** Plain reason for a version that failed processing (from its `error_code`). */
export function processingFailureMessage(code: string | null | undefined): string {
  return (code && PROCESSING_ERRORS[code]) || "Processing failed";
}
