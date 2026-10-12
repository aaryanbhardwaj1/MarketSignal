// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const state = vi.hoisted(() => ({
  pathname: "/w/NORTHSTAR/evidence",
  workspaces: {} as { isPending: boolean; isError: boolean; data?: unknown },
  capabilities: {} as { isPending: boolean; data?: unknown },
}));

vi.mock("next/navigation", () => ({ usePathname: () => state.pathname }));
vi.mock("@/lib/api/hooks/core", () => ({
  useWorkspaces: () => state.workspaces,
  useCapabilities: () => state.capabilities,
}));

import { Sidebar } from "./sidebar";
import { visibleWorkspaces, WorkspaceControl } from "./workspace-control";

const WORKSPACES = [
  { id: "1", code: "NORTHSTAR", name: "Northstar Athletics - Gen Z Growth Engagement", description: null, default_persona: "", created_at: "" },
  { id: "2", code: "SOUTHPEAK", name: "Southpeak Outdoor", description: null, default_persona: "", created_at: "" },
  { id: "3", code: "T0A1B2C3D4E", name: "Harness workspace", description: null, default_persona: "", created_at: "" },
];

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  state.pathname = "/w/NORTHSTAR/evidence";
  state.workspaces = { isPending: false, isError: false, data: WORKSPACES };
  state.capabilities = { isPending: false, data: { generation: { available: false, reason: "DISABLED" } } };
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const links = () => Array.from(host.querySelectorAll<HTMLAnchorElement>("nav[aria-label='Primary'] a"));

describe("Sidebar", () => {
  it("renders both groups with product labels", () => {
    act(() => root.render(<Sidebar ws="NORTHSTAR" />));
    expect(host.textContent).toContain("MarketSignal");
    expect(host.textContent).toContain("Developer tools");
    expect(links().map((a) => a.textContent)).toEqual([
      "Overview",
      "Ask MarketSignal",
      "Growth Opportunities",
      "Analytics",
      "Evidence Library",
      "Telemetry",
      "RAG Evaluation",
    ]);
  });

  it("marks exactly the active section with aria-current", () => {
    state.pathname = "/w/NORTHSTAR/dev/telemetry/runs/abc";
    act(() => root.render(<Sidebar ws="NORTHSTAR" />));
    const current = links().filter((a) => a.getAttribute("aria-current") === "page");
    expect(current.map((a) => a.textContent)).toEqual(["Telemetry"]);
    expect(current[0].getAttribute("href")).toBe("/w/NORTHSTAR/dev/telemetry");
  });

  it("shows the workspace name, never the code", () => {
    act(() => root.render(<Sidebar ws="NORTHSTAR" />));
    expect(host.textContent).toContain("Northstar Athletics");
    expect(host.textContent).toContain("Gen Z Growth Engagement");
    expect(host.textContent).not.toContain("NORTHSTAR");
  });

  it("shows the live model status in plain words", () => {
    act(() => root.render(<Sidebar ws="NORTHSTAR" />));
    expect(host.textContent).toContain("Live model unavailable");
    state.capabilities = { isPending: false, data: { generation: { available: true, reason: null } } };
    act(() => root.render(<Sidebar ws="NORTHSTAR" />));
    expect(host.textContent).toContain("Live model available");
  });

  it("treats an unreachable capabilities endpoint as unavailable", () => {
    state.capabilities = { isPending: false, data: undefined };
    act(() => root.render(<Sidebar ws="NORTHSTAR" />));
    expect(host.textContent).toContain("Live model unavailable");
  });
});

describe("WorkspaceControl", () => {
  it("filters harness test codes", () => {
    expect(visibleWorkspaces(WORKSPACES as never).map((w) => w.code)).toEqual(["NORTHSTAR", "SOUTHPEAK"]);
  });

  it("lists only visible workspaces by name, keeping the current section", () => {
    state.pathname = "/w/NORTHSTAR/ask/abc";
    act(() => root.render(<WorkspaceControl ws="NORTHSTAR" />));
    const trigger = host.querySelector<HTMLButtonElement>("button[aria-expanded]")!;
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    act(() => trigger.click());
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    const items = Array.from(host.querySelectorAll<HTMLAnchorElement>("li a"));
    expect(items.map((a) => Array.from(a.querySelectorAll("span.block")).map((s) => s.textContent))).toEqual([
      ["Northstar Athletics", "Gen Z Growth Engagement"],
      ["Southpeak Outdoor"],
    ]);
    const lines = Array.from(trigger.querySelectorAll("span.block")).map((s) => s.textContent);
    expect(lines).toEqual(["Northstar Athletics", "Gen Z Growth Engagement"]);
    expect(items[1].getAttribute("href")).toBe("/w/SOUTHPEAK/ask");
    expect(host.textContent).not.toContain("Harness workspace");
    expect(host.textContent).not.toMatch(/T[0-9A-F]{10}/);
  });

  it("closes the popover on Escape and returns focus to the trigger", () => {
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
    expect(host.querySelector<HTMLButtonElement>("button")!.disabled).toBe(true);
  });
});
