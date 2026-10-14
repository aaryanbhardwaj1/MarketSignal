import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { SourceDetail, SourceVersion, VersionStatus } from "@/lib/api/types";
import { QUEUED_NOTICE_AFTER_MS } from "@/lib/attachments";
import { AttachmentChips, chipStatusText } from "./attachment-chips";
import { toView, type AttachmentView } from "./attachments-context";

type Record_ = Parameters<typeof toView>[0];

const record = (over: Partial<Record_> = {}): Record_ => ({
  id: "attachment-1",
  name: "notes.md",
  size: 2048,
  kind: "text",
  phase: "accepted",
  error: null,
  sourceId: "s1",
  versionId: "v1",
  acceptedAt: 1_000,
  duplicate: false,
  ...over,
});

const detail = (status: VersionStatus, errorCode: string | null = null): SourceDetail =>
  ({
    source_id: "s1",
    source_code: "NOTES",
    title: "notes",
    source_type: "markdown",
    deleted: false,
    current_version_id: null,
    versions: [{ version_id: "v1", status, error_code: errorCode } as SourceVersion],
  }) as SourceDetail;

describe("toView", () => {
  it("reports the upload request first, then the server's processing status", () => {
    expect(toView(record({ phase: "uploading" }), undefined, 0).status).toBe("uploading");
    expect(toView(record(), undefined, 1_000).status).toBe("processing");
    expect(toView(record(), detail("parsing"), 2_000).status).toBe("processing");
    expect(toView(record(), detail("ready"), 2_000)).toMatchObject({ status: "ready", reason: null });
  });

  it("shows a long wait in the queue as queued, not as an error", () => {
    expect(toView(record(), detail("queued"), 1_000 + QUEUED_NOTICE_AFTER_MS).status).toBe("queued");
  });

  it("carries a plain reason for rejected uploads and failed processing", () => {
    expect(toView(record({ phase: "rejected", error: "Unsupported file type" }), undefined, 0)).toMatchObject({
      status: "failed",
      reason: "Unsupported file type",
    });
    expect(toView(record(), detail("failed", "PARSE_FAILED"), 2_000)).toMatchObject({
      status: "failed",
      reason: "The file could not be read",
    });
  });
});

const view = (over: Partial<AttachmentView> = {}): AttachmentView => ({
  id: "attachment-1",
  name: "quarterly-customer-research-findings-final.pdf",
  size: 1536,
  kind: "pdf",
  status: "processing",
  reason: null,
  duplicate: false,
  ...over,
});

describe("AttachmentChips", () => {
  it("renders nothing without attachments", () => {
    expect(renderToStaticMarkup(<AttachmentChips items={[]} onRemove={() => {}} />)).toBe("");
  });

  it("shows a clipped name (full name on hover), size, status and a remove button", () => {
    const html = renderToStaticMarkup(<AttachmentChips items={[view()]} onRemove={() => {}} />);
    expect(html).toContain('aria-label="Attached files"');
    expect(html).toContain('title="quarterly-customer-research-findings-final.pdf"');
    expect(html).toMatch(/>quarterly[^<]*…\.pdf</);
    expect(html).toContain("1.5 KB");
    expect(html).toContain("Processing");
    expect(html).toContain('aria-label="Remove quarterly-customer-research-findings-final.pdf"');
  });

  it("words each status plainly", () => {
    expect(chipStatusText(view({ status: "uploading" }))).toBe("Uploading");
    expect(chipStatusText(view({ status: "queued" }))).toBe("Queued for processing");
    expect(chipStatusText(view({ status: "ready" }))).toBe("Ready");
    expect(chipStatusText(view({ status: "ready", duplicate: true }))).toBe("Already in workspace");
    expect(chipStatusText(view({ status: "failed", reason: "File too large (max 25 MB)" }))).toBe("File too large (max 25 MB)");
  });
});
