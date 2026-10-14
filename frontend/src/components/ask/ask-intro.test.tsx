// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationSummary } from "@/lib/api/contracts";
import { AskIntro, EXAMPLE_QUESTIONS, savedResearch } from "./ask-intro";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const fillComposer = vi.fn();
const conversations: { isPending: boolean; rows: ConversationSummary[] } = { isPending: false, rows: [] };

vi.mock("./ask-session", () => ({ useAskSession: () => ({ fillComposer }) }));
vi.mock("./composer", () => ({ Composer: () => <div data-testid="composer" /> }));
vi.mock("@/lib/api/hooks/core", () => ({
  useConversations: () => ({ isPending: conversations.isPending, data: { pages: [{ items: conversations.rows }] } }),
}));

const convo = (id: string, title: string, mode: "standard" | "research" = "research"): ConversationSummary => ({
  conversation_id: id,
  title,
  title_source: "title",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  message_count: 2,
  featured: true,
  last_run: {
    run_id: `r-${id}`,
    mode,
    status: "succeeded",
    termination_state: "completed",
    degradation_flags: [],
    created_at: "2026-01-01T00:00:00Z",
    finished_at: "2026-01-01T00:01:00Z",
  },
});

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  fillComposer.mockClear();
  conversations.isPending = false;
  conversations.rows = [];
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

describe("AskIntro", () => {
  it("leads with the question, explains the product and offers the five example questions", () => {
    act(() => root.render(<AskIntro ws="NORTHSTAR" />));
    expect(host.querySelector("h1")?.textContent).toBe("What do you want to investigate?");
    expect(host.textContent).toContain("citing the passages it relies on");
    const examples = [...host.querySelectorAll('[aria-labelledby="examples-heading"] button')].map((b) => b.textContent);
    expect(examples).toEqual([...EXAMPLE_QUESTIONS]);
    expect(host.querySelector('[data-testid="composer"]')).not.toBeNull();
  });

  it("fills the composer (without sending) when an example is chosen", () => {
    act(() => root.render(<AskIntro ws="NORTHSTAR" />));
    const button = host.querySelector('[aria-labelledby="examples-heading"] button') as HTMLButtonElement;
    act(() => button.click());
    expect(fillComposer).toHaveBeenCalledWith(EXAMPLE_QUESTIONS[0]);
  });

  it("shows up to three saved research answers that open their conversation", () => {
    conversations.rows = [
      convo("a", "Churn drivers", "research"),
      convo("b", "Churn drivers", "standard"),
      convo("c", "Pricing gaps"),
      convo("d", "Competitor moves"),
      convo("e", "Fourth question"),
    ];
    act(() => root.render(<AskIntro ws="NORTHSTAR" />));
    const section = host.querySelector("#saved-research");
    expect(section?.textContent).toContain("Saved research");
    expect(section?.textContent).toContain("Verified answers with cited evidence");
    const links = [...(section?.querySelectorAll("a") ?? [])];
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/w/NORTHSTAR/ask/a", "/w/NORTHSTAR/ask/c", "/w/NORTHSTAR/ask/d"]);
    expect(links[0].textContent).toContain("Research and Standard answers");
  });

  it("omits the saved research strip when nothing is saved", () => {
    act(() => root.render(<AskIntro ws="NORTHSTAR" />));
    expect(host.querySelector("#saved-research")).toBeNull();
  });
});

describe("savedResearch", () => {
  it("keeps one entry per question and caps the list", () => {
    const rows = [convo("a", "Q1"), convo("b", "Q1"), convo("c", "Q2")];
    expect(savedResearch(rows).map((r) => r.conversation_id)).toEqual(["a", "c"]);
    expect(savedResearch(rows, 1)).toHaveLength(1);
  });
});
