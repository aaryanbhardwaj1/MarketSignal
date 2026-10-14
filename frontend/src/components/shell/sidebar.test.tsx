// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

type Query = { isPending: boolean; isError: boolean; data?: unknown };
type Infinite = Query & { hasNextPage?: boolean; isFetchingNextPage?: boolean; isFetchNextPageError?: boolean; fetchNextPage: () => Promise<void> };

const state = vi.hoisted(() => ({
  pathname: "/w/NORTHSTAR/evidence",
  params: {} as Record<string, string>,
  workspaces: {} as { isPending: boolean; isError: boolean; data?: unknown },
  capabilities: {} as { isPending: boolean; data?: unknown },
  featured: {} as Infinite,
  all: {} as Infinite,
}));

vi.mock("next/navigation", () => ({ usePathname: () => state.pathname, useParams: () => state.params }));
vi.mock("@/lib/api/hooks/core", () => ({
  useWorkspaces: () => state.workspaces,
  useCapabilities: () => state.capabilities,
  useConversations: (_ws: string, filters: { featured?: boolean }) => (filters.featured ? state.featured : state.all),
}));

import { ConversationSidebar } from "./conversation-sidebar";
import { NewChatSignalProvider, useNewChatSignal } from "./new-chat-signal";
import { TopBar } from "./top-bar";
import { visibleWorkspaces, WorkspaceControl } from "./workspace-control";

const WORKSPACES = [
  { id: "1", code: "NORTHSTAR", name: "Northstar Athletics - Gen Z Growth Engagement", description: null, default_persona: "", created_at: "" },
  { id: "2", code: "SOUTHPEAK", name: "Southpeak Outdoor", description: null, default_persona: "", created_at: "" },
  { id: "3", code: "T0A1B2C3D4E", name: "Harness workspace", description: null, default_persona: "", created_at: "" },
];

const NOW = new Date(2026, 9, 14, 10, 30);
const conv = (id: string, title: string, updated: Date, featured = false) => ({
  conversation_id: id,
  title,
  title_source: "title",
  created_at: updated.toISOString(),
  updated_at: updated.toISOString(),
  message_count: 2,
  featured,
  last_run: { run_id: `r-${id}`, mode: "research", status: "completed", termination_state: "final_answer", degradation_flags: [], created_at: "", finished_at: "" },
});
const page = (items: unknown[]) => ({ pages: [{ items, next_cursor: null }] });

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  state.pathname = "/w/NORTHSTAR/evidence";
  state.params = {};
  state.workspaces = { isPending: false, isError: false, data: WORKSPACES };
  state.capabilities = { isPending: false, data: { generation: { available: false, reason: "DISABLED" } } };
  const fetchNextPage = vi.fn(async () => {});
  state.featured = { isPending: false, isError: false, data: page([conv("f1", "Where should Northstar grow?", new Date(2026, 8, 1), true)]), fetchNextPage };
  state.all = {
    isPending: false,
    isError: false,
    data: page([
      conv("f1", "Where should Northstar grow?", new Date(2026, 8, 1), true),
      conv("t1", "Why is Gen Z churning?", new Date(2026, 9, 14, 9)),
      conv("y1", "Pricing tiers compared.", new Date(2026, 9, 13, 9)),
      conv("o1", "Old question", new Date(2025, 0, 1)),
    ]),
    hasNextPage: false,
    fetchNextPage,
  };
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  localStorage.clear();
});

const renderTopBar = () =>
  act(() => root.render(<TopBar ws="NORTHSTAR" menuOpen={false} onMenu={() => {}} menuButtonRef={{ current: null }} menuId="m" />));

describe("TopBar", () => {
  it("shows the four sections in order with workspace-scoped hrefs", () => {
    renderTopBar();
    const links = Array.from(host.querySelectorAll<HTMLAnchorElement>("nav[aria-label='Primary'] a"));
    expect(links.map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["Chat", "/w/NORTHSTAR/ask"],
      ["Insights", "/w/NORTHSTAR/insights"],
      ["Growth Opportunities", "/w/NORTHSTAR/opportunities"],
      ["Analytics", "/w/NORTHSTAR/analytics"],
    ]);
  });

  it("marks exactly the active section, including on the legacy overview path", () => {
    state.pathname = "/w/NORTHSTAR/overview";
    renderTopBar();
    const current = Array.from(host.querySelectorAll("a[aria-current='page']"));
    expect(current.map((a) => a.textContent)).toEqual(["Insights"]);
  });

  it("groups the developer tools and marks the active one", () => {
    state.pathname = "/w/NORTHSTAR/dev/telemetry/runs/abc";
    renderTopBar();
    const group = host.querySelector("[role='group'][aria-label='Developer tools']")!;
    const tools = Array.from(group.querySelectorAll<HTMLAnchorElement>("a"));
    expect(tools.map((a) => [a.getAttribute("aria-label"), a.getAttribute("href"), a.getAttribute("aria-current")])).toEqual([
      ["Telemetry", "/w/NORTHSTAR/dev/telemetry", "page"],
      ["RAG Evaluation", "/w/NORTHSTAR/dev/evaluation", null],
    ]);
    expect(host.querySelector("nav[aria-label='Primary'] a[aria-current]")).toBeNull();
  });

  it("states the live model status in plain words, unreachable counting as unavailable", () => {
    renderTopBar();
    expect(host.textContent).toContain("Live model unavailable");
    expect(host.textContent).toContain("saved research, evidence, analytics and insights still work");
    state.capabilities = { isPending: false, data: { generation: { available: true, reason: null } } };
    renderTopBar();
    expect(host.textContent).toContain("Live model available");
    state.capabilities = { isPending: false, data: undefined };
    renderTopBar();
    expect(host.textContent).toContain("Live model unavailable");
  });

  it("never shows a workspace code", () => {
    renderTopBar();
    expect(host.textContent).toContain("Northstar Athletics");
    expect(host.textContent).not.toContain("NORTHSTAR");
  });
});

describe("WorkspaceControl", () => {
  it("filters harness test codes", () => {
    expect(visibleWorkspaces(WORKSPACES as never).map((w) => w.code)).toEqual(["NORTHSTAR", "SOUTHPEAK"]);
  });

  it("opens a popover with the engagement, a switcher and the Evidence library link", () => {
    state.pathname = "/w/NORTHSTAR/ask/abc";
    act(() => root.render(<WorkspaceControl ws="NORTHSTAR" />));
    const trigger = host.querySelector<HTMLButtonElement>("button[aria-expanded]")!;
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    act(() => trigger.click());
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(host.textContent).toContain("Gen Z Growth Engagement");
    const items = Array.from(host.querySelectorAll<HTMLAnchorElement>("li a"));
    expect(items.map((a) => a.getAttribute("href"))).toEqual(["/w/NORTHSTAR/ask", "/w/SOUTHPEAK/ask"]);
    expect(items[0].getAttribute("aria-current")).toBe("true");
    const library = Array.from(host.querySelectorAll<HTMLAnchorElement>("a")).find((a) => a.textContent === "Evidence library");
    expect(library?.getAttribute("href")).toBe("/w/NORTHSTAR/evidence");
    expect(host.textContent).not.toContain("Harness workspace");
  });

  it("hides the switcher when only one workspace is visible", () => {
    state.workspaces = { isPending: false, isError: false, data: [WORKSPACES[0], WORKSPACES[2]] };
    act(() => root.render(<WorkspaceControl ws="NORTHSTAR" />));
    act(() => host.querySelector<HTMLButtonElement>("button")!.click());
    expect(host.textContent).not.toContain("Switch workspace");
    expect(host.textContent).toContain("Evidence library");
  });

  it("closes on Escape and returns focus to the trigger", () => {
    act(() => root.render(<WorkspaceControl ws="NORTHSTAR" />));
    const trigger = host.querySelector<HTMLButtonElement>("button[aria-expanded]")!;
    act(() => trigger.click());
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(trigger);
  });

  it("degrades without a workspace list", () => {
    state.workspaces = { isPending: false, isError: true, data: undefined };
    act(() => root.render(<WorkspaceControl ws="NORTHSTAR" />));
    expect(host.textContent).toContain("Workspace unavailable");
  });
});

describe("ConversationSidebar", () => {
  const headings = () => Array.from(host.querySelectorAll("h3")).map((h) => h.textContent);
  const rowTitles = () => Array.from(host.querySelectorAll("[data-conversation-row]")).map((a) => a.getAttribute("title"));

  it("lists Saved research first, then recency groups, without duplicates", () => {
    act(() => root.render(<ConversationSidebar ws="NORTHSTAR" now={NOW} />));
    expect(headings()).toEqual(["Saved research", "Today", "Yesterday", "Older"]);
    expect(rowTitles()).toEqual(["Where should Northstar grow", "Why is Gen Z churning", "Pricing tiers compared", "Old question"]);
  });

  it("highlights the open conversation", () => {
    state.params = { conversationId: "y1" };
    act(() => root.render(<ConversationSidebar ws="NORTHSTAR" now={NOW} />));
    const current = host.querySelector("[data-conversation-row][aria-current='page']");
    expect(current?.getAttribute("href")).toBe("/w/NORTHSTAR/ask/y1");
  });

  it("moves focus between rows with the arrow keys", () => {
    act(() => root.render(<ConversationSidebar ws="NORTHSTAR" now={NOW} />));
    const rows = Array.from(host.querySelectorAll<HTMLAnchorElement>("[data-conversation-row]"));
    rows[0].focus();
    act(() => {
      rows[0].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
    });
    expect(document.activeElement).toBe(rows[1]);
    act(() => {
      rows[1].dispatchEvent(new KeyboardEvent("keydown", { key: "End", bubbles: true }));
    });
    expect(document.activeElement).toBe(rows[3]);
  });

  it("signals New chat to subscribers", () => {
    const onNewChat = vi.fn();
    function Listener() {
      useNewChatSignal(onNewChat);
      return null;
    }
    act(() =>
      root.render(
        <NewChatSignalProvider>
          <Listener />
          <ConversationSidebar ws="NORTHSTAR" now={NOW} />
        </NewChatSignalProvider>,
      ),
    );
    const link = Array.from(host.querySelectorAll<HTMLAnchorElement>("a")).find((a) => a.textContent === "New chat")!;
    expect(link.getAttribute("href")).toBe("/w/NORTHSTAR/ask");
    act(() => link.click());
    expect(onNewChat).toHaveBeenCalledTimes(1);
  });

  it("shows the rail when collapsed and makes the full list inert", () => {
    act(() => root.render(<ConversationSidebar ws="NORTHSTAR" now={NOW} collapsed onToggle={() => {}} />));
    expect(host.querySelector("[aria-label='Expand sidebar']")).not.toBeNull();
    expect(host.querySelector("[aria-label='New chat']")).not.toBeNull();
    expect(host.querySelector("[aria-label='Search conversations']")).not.toBeNull();
    const list = host.querySelector("nav[aria-label='Conversations']")!;
    expect(list.closest("[inert]")).not.toBeNull();
  });
});
