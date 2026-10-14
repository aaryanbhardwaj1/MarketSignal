// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NewChatSignalProvider, useEmitNewChat } from "@/components/shell/new-chat-signal";
import { AskSessionProvider } from "./ask-session";
import { Composer } from "./composer";
import { MODEL_UNAVAILABLE_INLINE } from "./model-unavailable";
import { QuestionForm } from "./question-form";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const generation = { available: true };
const uploadSource = vi.fn<(...args: unknown[]) => Promise<never>>(() => new Promise<never>(() => {}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api/hooks/core", async (original) => ({
  ...(await original<typeof import("@/lib/api/hooks/core")>()),
  useCapabilities: () => ({ isPending: false, data: { generation: { available: generation.available, reason: null } } }),
}));
vi.mock("@/lib/api/endpoints", async (original) => ({
  ...(await original<typeof import("@/lib/api/endpoints")>()),
  uploadSource: (...args: unknown[]) => uploadSource(...args),
}));

let host: HTMLDivElement;
let root: Root;
const emitter: { emit: () => void } = { emit: () => {} };

function Emitter() {
  const emit = useEmitNewChat();
  useEffect(() => {
    emitter.emit = emit;
  }, [emit]);
  return null;
}

beforeEach(() => {
  generation.available = true;
  uploadSource.mockClear();
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

function renderComposer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  act(() =>
    root.render(
      <QueryClientProvider client={client}>
        <NewChatSignalProvider>
          <AskSessionProvider ws="NORTHSTAR">
            <Composer conversationId={null} />
            <Emitter />
          </AskSessionProvider>
        </NewChatSignalProvider>
      </QueryClientProvider>,
    ),
  );
}

const box = () => host.querySelector("textarea") as HTMLTextAreaElement;
const send = () => host.querySelector('button[type="submit"]') as HTMLButtonElement;

function type(text: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
  act(() => {
    setter?.call(box(), text);
    box().dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function attach(...files: File[]) {
  const input = host.querySelector('input[type="file"]') as HTMLInputElement;
  Object.defineProperty(input, "files", { configurable: true, value: files });
  act(() => {
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

function press(init: KeyboardEventInit) {
  act(() => {
    box().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true, ...init }));
  });
}

describe("Composer", () => {
  it("New chat clears the draft and the attachments and focuses the box", () => {
    renderComposer();
    type("Where is churn rising?");
    attach(new File(["# notes"], "notes.md", { type: "text/markdown" }));
    expect(box().value).toBe("Where is churn rising?");
    expect(host.textContent).toContain("notes.md");
    expect(host.textContent).toContain("Uploading");
    expect(uploadSource).toHaveBeenCalledTimes(1);

    act(() => emitter.emit());

    expect(box().value).toBe("");
    expect(host.textContent).not.toContain("notes.md");
    expect(document.activeElement).toBe(box());
  });

  it("rejects unsupported files on the client without uploading them", () => {
    renderComposer();
    attach(new File(["x"], "deck.key"));
    expect(host.textContent).toContain("Unsupported file type");
    expect(uploadSource).not.toHaveBeenCalled();
  });

  it("offline: send is disabled with one calm line, attaching still works", () => {
    generation.available = false;
    renderComposer();
    expect(send().disabled).toBe(true);
    expect(box().disabled).toBe(true);
    expect(host.textContent).toContain(MODEL_UNAVAILABLE_INLINE);
    expect(host.querySelector('a[href="/w/NORTHSTAR/ask#saved-research"]')).not.toBeNull();
    const clip = host.querySelector('button[aria-label="Attach files"]') as HTMLButtonElement;
    expect(clip.disabled).toBe(false);
    attach(new File(["# notes"], "notes.md"));
    expect(uploadSource).toHaveBeenCalledTimes(1);
  });
});

describe("QuestionForm keyboard", () => {
  it("Enter and Cmd/Ctrl+Enter send; Shift+Enter does not", () => {
    const onSubmit = vi.fn(async () => false);
    act(() => root.render(<QuestionForm disabled={false} busy={false} onSubmit={onSubmit} />));
    type("What blocks conversion?");
    press({ shiftKey: true });
    expect(onSubmit).not.toHaveBeenCalled();
    press({});
    expect(onSubmit).toHaveBeenLastCalledWith("What blocks conversion?", "auto");
    press({ ctrlKey: true });
    press({ metaKey: true, shiftKey: true });
    expect(onSubmit).toHaveBeenCalledTimes(3);
  });

  it("does not send an empty question", () => {
    const onSubmit = vi.fn(async () => true);
    act(() => root.render(<QuestionForm disabled={false} busy={false} onSubmit={onSubmit} />));
    type("   ");
    press({});
    expect(onSubmit).not.toHaveBeenCalled();
    expect(send().disabled).toBe(true);
  });
});
