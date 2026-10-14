// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { DeckDownload, type DeckDownloader } from "./deck-download";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const BODY = { signal_ids: ["s1"], opportunity_ids: [], analysis_ids: [] };
let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const button = () => host.querySelector("button") as HTMLButtonElement;
const status = () => host.querySelector('[role="status"]')?.textContent ?? "";

describe("DeckDownload", () => {
  it("shows the saved state only after the file was saved", async () => {
    const pending = deferred<{ filename: string; bytes: number }>();
    const download = vi.fn<DeckDownloader>(() => pending.promise);
    act(() => root.render(<DeckDownload ws="NORTHSTAR" body={BODY} download={download} />));
    expect(button().textContent).toBe("Download .pptx");

    act(() => button().click());
    expect(download).toHaveBeenCalledWith("NORTHSTAR", BODY, expect.any(AbortSignal));
    expect(button().textContent).toBe("Preparing file…");
    expect(button().getAttribute("aria-busy")).toBe("true");
    expect(status()).toBe("");

    await act(async () => pending.resolve({ filename: "strategic-findings.pptx", bytes: 10 }));
    expect(status()).toContain("Saved strategic-findings.pptx");
    expect(button().textContent).toBe("Download again");
  });

  it("explains failures plainly and allows a retry", async () => {
    const download = vi.fn<DeckDownloader>(() => Promise.reject(new ApiError(422, "DECK_EMPTY", "empty")));
    act(() => root.render(<DeckDownload ws="NORTHSTAR" body={BODY} download={download} />));
    await act(async () => button().click());
    expect(status()).toContain("The file could not be created.");
    expect(status()).toContain("nothing to put in a presentation");
    expect(status()).not.toContain("DECK_EMPTY");
    expect(button().textContent).toBe("Download .pptx");
  });

  it("starts from the generation outcome", () => {
    const download = vi.fn<DeckDownloader>();
    act(() => root.render(<DeckDownload ws="N" body={BODY} download={download} initial={{ status: "saved", filename: "deck.pptx" }} />));
    expect(status()).toContain("Saved deck.pptx");
    expect(download).not.toHaveBeenCalled();
  });
});
