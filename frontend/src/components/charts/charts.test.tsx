// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { EvidenceBalance } from "./evidence-balance";
import { HBarChart } from "./hbar-chart";
import { LineChart } from "./line-chart";
import { StageBreakdown, stageLayout } from "./stage-breakdown";
import { StackedBar } from "./stacked-bar";

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

describe("stageLayout", () => {
  it("runs stages back to back unless a start is given", () => {
    const { total, rows } = stageLayout([
      { label: "a", duration: 100 },
      { label: "b", duration: 300 },
      { label: "c", duration: 100, start: 50 },
    ]);
    expect(total).toBe(400);
    expect(rows.map((r) => [r.start, r.offset, r.share])).toEqual([
      [0, 0, 0.25],
      [100, 0.25, 0.75],
      [50, 0.125, 0.25],
    ]);
  });
});

describe("chart accessibility contract", () => {
  it("HBarChart renders a figure, labelled image and hidden table", () => {
    act(() =>
      root.render(<HBarChart ariaLabel="Spend by channel" caption="Sample" data={[{ label: "Social", value: 42, emphasis: true }, { label: "Search", value: 18 }]} />),
    );
    expect(host.querySelector("figure figcaption")!.textContent).toBe("Sample");
    expect(host.querySelector("[role='img']")!.getAttribute("aria-label")).toBe("Spend by channel");
    const cells = Array.from(host.querySelectorAll("table.sr-only tbody tr")).map((tr) => tr.textContent);
    expect(cells).toEqual(["Social42", "Search18"]);
  });

  it("shows an honest empty state instead of a chart", () => {
    act(() => root.render(<HBarChart ariaLabel="x" data={[]} />));
    expect(host.querySelector("figure")).toBeNull();
    expect(host.textContent).toContain("No data to chart yet.");
  });

  it("LineChart moves its tooltip with the arrow keys", () => {
    act(() => root.render(<LineChart ariaLabel="Trend" x={["Q1", "Q2", "Q3"]} series={[{ name: "Share", values: [1, 2, 3] }]} />));
    const focusable = host.querySelector<HTMLElement>("[tabindex='0']")!;
    act(() => {
      focusable.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    });
    expect(host.querySelector("[aria-live='polite']")!.textContent).toContain("Q1");
  });

  it("StackedBar, EvidenceBalance and StageBreakdown print their numbers", () => {
    act(() =>
      root.render(
        <>
          <StackedBar ariaLabel="Mix" segments={[{ label: "A", value: 1 }, { label: "B", value: 3 }]} />
          <EvidenceBalance supporting={5} contradicting={2} />
          <StageBreakdown ariaLabel="Timing" stages={[{ label: "Retrieve", duration: 120 }]} />
        </>,
      ),
    );
    expect(host.textContent).toContain("75%");
    expect(host.querySelectorAll("[role='img']")[1].getAttribute("aria-label")).toBe("Supporting: 5 sources; Contradicting: 2 sources");
    expect(host.textContent).toContain("120 ms");
  });
});
