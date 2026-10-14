// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { SignalLoader } from "./signal-loader";
import { StageProgress, stageSummary, type Stage } from "./stage-progress";
import { transitionKey } from "./page-transition";

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

const STAGES: Stage[] = [
  { id: "plan", label: "Plan", state: "done", timing: "0.4 s" },
  { id: "retrieve", label: "Retrieve evidence", state: "active" },
  { id: "skip", label: "Analytics", state: "skipped" },
  { id: "verify", label: "Verify", state: "pending" },
];

describe("transitionKey", () => {
  it.each([
    ["/w/NORTHSTAR/ask", "NORTHSTAR/ask"],
    ["/w/NORTHSTAR/ask/abc", "NORTHSTAR/ask"],
    ["/w/NORTHSTAR/dev/telemetry/runs/1", "NORTHSTAR/dev/telemetry"],
    ["/w/NORTHSTAR/dev/evaluation?tab=x", "NORTHSTAR/dev/evaluation"],
    ["/w/NORTHSTAR", "NORTHSTAR"],
    ["/dev-design", "dev-design"],
  ])("%s → %s", (path, key) => expect(transitionKey(path)).toBe(key));
});

describe("StageProgress", () => {
  it("marks the active step and spells out every state", () => {
    act(() => root.render(<StageProgress stages={STAGES} label="Research progress" />));
    const list = host.querySelector("ol")!;
    expect(list.getAttribute("aria-label")).toBe("Research progress");
    const items = Array.from(list.querySelectorAll("li"));
    expect(items).toHaveLength(4);
    expect(items[1].getAttribute("aria-current")).toBe("step");
    expect(items[0].textContent).toContain("Done");
    expect(items[0].textContent).toContain("0.4 s");
    expect(items[2].textContent).toContain("Skipped");
    expect(items[3].textContent).toContain("Not started");
  });

  it("renders the compact horizontal variant", () => {
    act(() => root.render(<StageProgress stages={STAGES} orientation="horizontal" />));
    expect(host.querySelectorAll("li")).toHaveLength(4);
    expect(host.querySelector("[aria-current='step']")!.textContent).toContain("Retrieve evidence");
  });

  it("summarises progress", () => {
    expect(stageSummary(STAGES)).toBe("2 of 4 stages done");
    expect(stageSummary([...STAGES, { id: "x", label: "X", state: "failed" }])).toBe("2 of 5 stages done, one failed");
  });
});

describe("SignalLoader", () => {
  it("is a labelled status", () => {
    act(() => root.render(<SignalLoader label="Retrieving evidence" />));
    const status = host.querySelector("[role='status']")!;
    expect(status.textContent).toBe("Retrieving evidence");
  });
});
