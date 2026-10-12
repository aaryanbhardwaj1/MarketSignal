// @vitest-environment jsdom
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { Dialog, Drawer } from "./drawer";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

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

function Harness({ kind }: { kind: "drawer" | "dialog" }) {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  return (
    <>
      <button type="button" id="opener" onClick={() => setOpen(true)}>
        Open
      </button>
      {kind === "drawer" ? (
        <Drawer open={open} onClose={close} title="Evidence passage" subtitle="Customer research">
          <p>Passage body</p>
        </Drawer>
      ) : (
        <Dialog open={open} onClose={close} title="Confirm">
          <p>Dialog body</p>
        </Dialog>
      )}
    </>
  );
}

function dialogEl(): HTMLDialogElement {
  const el = host.querySelector("dialog");
  if (!el) throw new Error("no dialog");
  return el;
}

describe.each(["drawer", "dialog"] as const)("%s", (kind) => {
  it("is closed and renders no body until opened", () => {
    act(() => root.render(<Harness kind={kind} />));
    expect(dialogEl().hasAttribute("open")).toBe(false);
    expect(host.textContent).not.toContain("body");
  });

  it("opens with a labelled title", () => {
    act(() => root.render(<Harness kind={kind} />));
    const opener = host.querySelector<HTMLButtonElement>("#opener")!;
    opener.focus();
    act(() => opener.click());
    const dialog = dialogEl();
    expect(dialog.hasAttribute("open")).toBe(true);
    const labelId = dialog.getAttribute("aria-labelledby")!;
    expect(document.getElementById(labelId)?.textContent).toBe(kind === "drawer" ? "Evidence passage" : "Confirm");
  });

  it("closes on Esc (cancel event) and returns focus to the opener", () => {
    act(() => root.render(<Harness kind={kind} />));
    const opener = host.querySelector<HTMLButtonElement>("#opener")!;
    opener.focus();
    act(() => opener.click());
    // Move focus into the dialog, as showModal() would.
    host.querySelector<HTMLElement>("dialog button, dialog p")?.focus();
    act(() => {
      dialogEl().dispatchEvent(new Event("cancel", { cancelable: true }));
    });
    expect(dialogEl().hasAttribute("open")).toBe(false);
    expect(document.activeElement).toBe(opener);
  });
});

describe("drawer close button", () => {
  it("closes the drawer", () => {
    act(() => root.render(<Harness kind="drawer" />));
    act(() => host.querySelector<HTMLButtonElement>("#opener")!.click());
    const close = host.querySelector<HTMLButtonElement>('button[aria-label="Close"]')!;
    act(() => close.click());
    expect(dialogEl().hasAttribute("open")).toBe(false);
  });
});
