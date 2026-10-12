// @vitest-environment jsdom
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/w/NORTHSTAR/dev/telemetry",
  useSearchParams: () => new URLSearchParams(search),
}));

import { TabPanel, Tabs } from "./tabs";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "runs", label: "Runs", count: 12 },
  { id: "tools", label: "Tools" },
];

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  replace.mockReset();
  search = "";
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

function Controlled() {
  const [value, setValue] = useState("overview");
  return (
    <>
      <Tabs label="Sections" idPrefix="t" tabs={TABS} value={value} onChange={setValue} />
      {TABS.map((t) => (
        <TabPanel key={t.id} idPrefix="t" id={t.id} hidden={t.id !== value}>
          {t.label} panel
        </TabPanel>
      ))}
    </>
  );
}

const tabs = () => Array.from(host.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
const key = (k: string) =>
  act(() => {
    document.activeElement!.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true }));
  });

describe("Tabs", () => {
  it("renders an ARIA tablist wired to its panels with a roving tabindex", () => {
    act(() => root.render(<Controlled />));
    expect(host.querySelector('[role="tablist"]')?.getAttribute("aria-label")).toBe("Sections");
    const [first, second] = tabs();
    expect(first.getAttribute("aria-selected")).toBe("true");
    expect(first.tabIndex).toBe(0);
    expect(second.tabIndex).toBe(-1);
    expect(first.getAttribute("aria-controls")).toBe("t-panel-overview");
    expect(second.hasAttribute("aria-controls")).toBe(false);
    expect(document.getElementById("t-panel-overview")?.getAttribute("aria-labelledby")).toBe("t-tab-overview");
    expect(second.textContent).toContain("12");
  });

  it("moves selection and focus with arrow keys, Home and End (wrapping)", () => {
    act(() => root.render(<Controlled />));
    tabs()[0].focus();
    key("ArrowRight");
    expect(tabs()[1].getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(tabs()[1]);
    key("End");
    expect(tabs()[2].getAttribute("aria-selected")).toBe("true");
    key("ArrowRight");
    expect(tabs()[0].getAttribute("aria-selected")).toBe("true");
    key("ArrowLeft");
    expect(tabs()[2].getAttribute("aria-selected")).toBe("true");
    key("Home");
    expect(document.activeElement).toBe(tabs()[0]);
    expect(document.getElementById("t-panel-overview")?.hidden).toBe(false);
    expect(document.getElementById("t-panel-runs")?.hidden).toBe(true);
  });

  it("with `param`, reads the selected tab from the URL and writes changes back", () => {
    search = "view=runs&since=7d";
    act(() => root.render(<Tabs label="Sections" tabs={TABS} value="overview" param="view" />));
    expect(tabs()[1].getAttribute("aria-selected")).toBe("true");
    act(() => tabs()[2].click());
    expect(replace).toHaveBeenCalledWith("/w/NORTHSTAR/dev/telemetry?view=tools&since=7d", { scroll: false });
  });

  it("with `param`, ignores an unknown URL value and falls back to `value`", () => {
    search = "view=bogus";
    act(() => root.render(<Tabs label="Sections" tabs={TABS} value="overview" param="view" />));
    expect(tabs()[0].getAttribute("aria-selected")).toBe("true");
  });
});
