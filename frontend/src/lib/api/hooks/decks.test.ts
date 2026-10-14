import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DeckPreviewResponse } from "../contracts";
import { ApiError, NETWORK_ERROR } from "../errors";
import { DEFAULT_DECK_FILENAME, downloadDeckPptx, PPTX_MIME, previewDeck } from "./decks";

const saveBlob = vi.fn();
vi.mock("../../download", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../download")>()),
  saveBlob: (blob: Blob, name: string) => saveBlob(blob, name),
}));

const BODY = { signal_ids: ["premium-ceiling"], opportunity_ids: ["O2"] };
const PREVIEW: DeckPreviewResponse = {
  deck: {
    title: "Strategic findings: Northstar",
    question: null,
    workspace: { code: "NORTHSTAR", name: "Northstar" },
    generated_at: "2026-10-14T09:30:00+00:00",
    fixture_version: "NORTHSTAR.v2",
    slides: [{ index: 1, kind: "title", title: "Strategic findings: Northstar", subtitle: null, blocks: [], notes: [] }],
    sources: [],
    excluded: [],
    counts: { items: 2, sources: 0, slides: 1 },
  },
};

function stubFetch(response: Response): ReturnType<typeof vi.fn> {
  const fetch = vi.fn(async () => response);
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const call = (fetch: ReturnType<typeof vi.fn>): [string, RequestInit] =>
  fetch.mock.calls[0] as unknown as [string, RequestInit];

beforeEach(() => saveBlob.mockReset());
afterEach(() => vi.unstubAllGlobals());

describe("previewDeck", () => {
  it("posts the selection to the workspace preview route", async () => {
    const fetch = stubFetch(new Response(JSON.stringify(PREVIEW), { status: 200 }));
    await expect(previewDeck("NORTH STAR", BODY)).resolves.toEqual(PREVIEW);
    const [url, init] = call(fetch);
    expect(new URL(url).pathname).toBe("/api/workspaces/NORTH%20STAR/decks/preview");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual(BODY);
  });

  it("surfaces unknown ids as an ApiError with details", async () => {
    const error = { error: { code: "DECK_ITEMS_NOT_FOUND", message: "not found", unknown: ["O9"] } };
    stubFetch(new Response(JSON.stringify(error), { status: 422 }));
    const failure = previewDeck("NORTHSTAR", { opportunity_ids: ["O9"] });
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({ status: 422, code: "DECK_ITEMS_NOT_FOUND", details: { unknown: ["O9"] } });
  });
});

describe("downloadDeckPptx", () => {
  it("saves the returned bytes under the server's file name", async () => {
    const fetch = stubFetch(
      new Response(new Uint8Array([80, 75, 3, 4]), {
        status: 200,
        headers: { "Content-Type": PPTX_MIME, "Content-Disposition": 'attachment; filename="Gen-Z-growth.pptx"' },
      }),
    );
    await expect(downloadDeckPptx("NORTHSTAR", BODY)).resolves.toEqual({ filename: "Gen-Z-growth.pptx", bytes: 4 });
    const [url, init] = call(fetch);
    expect(new URL(url).pathname).toBe("/api/workspaces/NORTHSTAR/decks/pptx");
    expect(init.method).toBe("POST");
    expect(saveBlob).toHaveBeenCalledOnce();
    expect(saveBlob.mock.calls[0]?.[1]).toBe("Gen-Z-growth.pptx");
  });

  it("falls back to a default name without a Content-Disposition header", async () => {
    stubFetch(new Response(new Uint8Array([1]), { status: 200 }));
    await expect(downloadDeckPptx("NORTHSTAR", BODY)).resolves.toMatchObject({ filename: DEFAULT_DECK_FILENAME });
  });

  it("raises the API error and saves nothing when the deck is empty", async () => {
    const error = { error: { code: "DECK_EMPTY", message: "none verified", excluded: [] } };
    stubFetch(new Response(JSON.stringify(error), { status: 422 }));
    await expect(downloadDeckPptx("NORTHSTAR", BODY)).rejects.toMatchObject({ status: 422, code: "DECK_EMPTY" });
    expect(saveBlob).not.toHaveBeenCalled();
  });

  it("reports an unreachable API as a network error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );
    await expect(downloadDeckPptx("NORTHSTAR", BODY)).rejects.toMatchObject({ status: 0, code: NETWORK_ERROR });
  });
});
