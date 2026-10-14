import { describe, expect, it } from "vitest";
import { ApiError, NETWORK_ERROR } from "./api/errors";
import {
  ATTACHMENT_ACCEPT,
  ATTACHMENT_MAX_BYTES,
  attachmentKind,
  attachmentStatus,
  attachmentStatusLabel,
  clipFileName,
  isSettled,
  processingFailureMessage,
  QUEUED_NOTICE_AFTER_MS,
  uploadErrorMessage,
  validateAttachment,
} from "./attachments";

describe("validateAttachment", () => {
  it("accepts every extension the server accepts, case-insensitively", () => {
    for (const name of ["a.pdf", "b.DOCX", "c.pptx", "d.xlsx", "e.csv", "f.md", "g.markdown", "h.txt"]) {
      expect(validateAttachment({ name, size: 10 })).toEqual({ ok: true });
    }
  });

  it("rejects unsupported types, empty files and files over the limit", () => {
    expect(validateAttachment({ name: "deck.key", size: 10 })).toEqual({ ok: false, reason: "Unsupported file type" });
    expect(validateAttachment({ name: "noext", size: 10 })).toEqual({ ok: false, reason: "Unsupported file type" });
    expect(validateAttachment({ name: "a.md", size: 0 })).toEqual({ ok: false, reason: "Empty file" });
    expect(validateAttachment({ name: "a.pdf", size: ATTACHMENT_MAX_BYTES })).toEqual({ ok: true });
    expect(validateAttachment({ name: "a.pdf", size: ATTACHMENT_MAX_BYTES + 1 })).toEqual({
      ok: false,
      reason: "File too large (max 25 MB)",
    });
  });

  it("limits the file picker to the same extensions", () => {
    expect(ATTACHMENT_ACCEPT.split(",")).toEqual([".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".md", ".markdown", ".txt"]);
  });
});

describe("attachmentKind", () => {
  it("groups extensions into icon kinds", () => {
    expect(attachmentKind("r.pdf")).toBe("pdf");
    expect(attachmentKind("r.docx")).toBe("document");
    expect(attachmentKind("r.pptx")).toBe("presentation");
    expect(attachmentKind("r.xlsx")).toBe("spreadsheet");
    expect(attachmentKind("r.CSV")).toBe("spreadsheet");
    expect(attachmentKind("r.md")).toBe("text");
    expect(attachmentKind("r.txt")).toBe("text");
    expect(attachmentKind("r.zip")).toBe("other");
  });
});

describe("clipFileName", () => {
  it("leaves short names alone", () => {
    expect(clipFileName("notes.md")).toBe("notes.md");
  });

  it("clips long names in the middle and keeps the extension", () => {
    const clipped = clipFileName("quarterly-customer-research-findings-final-v3.pdf", 24);
    expect(clipped).toHaveLength(24);
    expect(clipped).toContain("…");
    expect(clipped.endsWith(".pdf")).toBe(true);
    expect(clipped.startsWith("quarterly")).toBe(true);
  });

  it("clips names without an extension", () => {
    const clipped = clipFileName("a".repeat(40), 10);
    expect(clipped).toHaveLength(10);
    expect(clipped.endsWith("…")).toBe(true);
  });
});

describe("attachmentStatus", () => {
  it("maps server version statuses to chip statuses", () => {
    expect(attachmentStatus("parsing", 0)).toBe("processing");
    expect(attachmentStatus("embedding", 60_000)).toBe("processing");
    expect(attachmentStatus("ready", 0)).toBe("ready");
    expect(attachmentStatus("ready_degraded", 0)).toBe("ready");
    expect(attachmentStatus("superseded", 0)).toBe("ready");
    expect(attachmentStatus("failed", 0)).toBe("failed");
    expect(attachmentStatus("purged", 0)).toBe("failed");
  });

  it("shows a queued file as processing at first, then as queued (never as an error)", () => {
    expect(attachmentStatus("queued", 0)).toBe("processing");
    expect(attachmentStatus("queued", QUEUED_NOTICE_AFTER_MS - 1)).toBe("processing");
    expect(attachmentStatus("queued", QUEUED_NOTICE_AFTER_MS)).toBe("queued");
  });

  it("labels each status in plain words", () => {
    expect(attachmentStatusLabel("uploading")).toBe("Uploading");
    expect(attachmentStatusLabel("processing")).toBe("Processing");
    expect(attachmentStatusLabel("queued")).toBe("Queued for processing");
    expect(attachmentStatusLabel("ready")).toBe("Ready");
    expect(attachmentStatusLabel("failed")).toBe("Failed");
    expect(isSettled("ready")).toBe(true);
    expect(isSettled("failed")).toBe(true);
    expect(isSettled("queued")).toBe(false);
    expect(isSettled("uploading")).toBe(false);
  });
});

describe("uploadErrorMessage", () => {
  it("turns server rejections into plain messages", () => {
    expect(uploadErrorMessage(new ApiError(415, "UNSUPPORTED_TYPE", "unsupported file type: .exe"))).toBe("Unsupported file type");
    expect(uploadErrorMessage(new ApiError(413, "FILE_TOO_LARGE", "x"))).toBe("File too large (max 25 MB)");
    expect(uploadErrorMessage(new ApiError(422, "ENCRYPTED_DOCUMENT", "x"))).toBe("Encrypted or password-protected file");
    expect(uploadErrorMessage(new ApiError(422, "EMPTY_DOCUMENT", "x"))).toBe("Empty file");
    expect(uploadErrorMessage(new ApiError(0, NETWORK_ERROR, "x"))).toBe("Cannot reach the server");
    expect(uploadErrorMessage(new ApiError(500, "INTERNAL", "boom"))).toBe("Upload failed");
    expect(uploadErrorMessage(new Error("boom"))).toBe("Upload failed");
  });

  it("explains processing failures without raw codes", () => {
    expect(processingFailureMessage("PARSE_FAILED")).toBe("The file could not be read");
    expect(processingFailureMessage("EMBEDDER_UNAVAILABLE")).toBe("Search indexing is unavailable");
    expect(processingFailureMessage("SOMETHING_NEW")).toBe("Processing failed");
    expect(processingFailureMessage(null)).toBe("Processing failed");
  });
});
