import { afterEach, describe, expect, it, vi } from "vitest";
import { filenameFromDisposition, saveBlob } from "./download";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("filenameFromDisposition", () => {
  it("reads a quoted filename", () => {
    expect(filenameFromDisposition('attachment; filename="Strategic-findings.pptx"', "x.pptx")).toBe(
      "Strategic-findings.pptx",
    );
  });

  it("strips paths, unsafe characters and leading dots", () => {
    expect(filenameFromDisposition('attachment; filename="../../etc/pass wd.pptx"', "x")).toBe("pass-wd.pptx");
    expect(filenameFromDisposition("attachment; filename=..hidden", "x")).toBe("hidden");
  });

  it("falls back when the header is missing or empty", () => {
    expect(filenameFromDisposition(null, "deck.pptx")).toBe("deck.pptx");
    expect(filenameFromDisposition('attachment; filename=""', "deck.pptx")).toBe("deck.pptx");
  });
});

describe("saveBlob", () => {
  it("clicks a temporary anchor and revokes the object URL", () => {
    vi.useFakeTimers();
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:deck");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const anchor = { href: "", download: "", rel: "", style: { display: "" }, click: vi.fn(), remove: vi.fn() };
    const appendChild = vi.fn();
    vi.stubGlobal("document", { createElement: vi.fn(() => anchor), body: { appendChild } });

    const blob = new Blob(["pptx"]);
    saveBlob(blob, "deck.pptx");

    expect(create).toHaveBeenCalledWith(blob);
    expect(appendChild).toHaveBeenCalledWith(anchor);
    expect(anchor).toMatchObject({ href: "blob:deck", download: "deck.pptx", rel: "noopener" });
    expect(anchor.click).toHaveBeenCalledOnce();
    expect(anchor.remove).toHaveBeenCalledOnce();
    expect(revoke).not.toHaveBeenCalled();
    vi.runAllTimers();
    expect(revoke).toHaveBeenCalledWith("blob:deck");
  });
});
