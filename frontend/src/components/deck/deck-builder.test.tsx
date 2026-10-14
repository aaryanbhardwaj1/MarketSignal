// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DeckPreviewResponse } from "@/lib/api/contracts";
import { parseDeckSelection } from "@/lib/views/insights";
import fixture from "./__fixtures__/deck-preview.json";
import { DeckBuilder } from "./deck-builder";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const BRIEF = {
  signals: [
    { id: "price-ceiling", kind: "emerging_signal", title: "Price ceiling", status: "strong_evidence", claim_type: "observed" },
    { id: "loyalty-lapse", kind: "risk_blocker", title: "Loyalty lapse", status: "emerging", claim_type: "inference" },
  ],
  opportunities: [{ id: "O2", title: "Premium personalization tier", status: "supported", thesis_claim_type: "hypothesis" }],
};
const ANALYSES = { analyses: [{ id: "wtp", title: "Willingness to pay", status: "computed", business_area: "Willingness to pay" }] };
const query = (data: unknown) => ({ data, isPending: false, isError: false, error: null, refetch: vi.fn() });
const outline = vi.fn<(ws: string, body: unknown) => unknown>(() => ({
  data: fixture as DeckPreviewResponse,
  isFetching: false,
  isError: false,
  error: null,
  settling: false,
}));

vi.mock("@/lib/api/hooks/insights", () => ({
  useInsights: () => query(BRIEF),
  useAnalyses: () => query(ANALYSES),
}));
vi.mock("./use-deck-generation", () => ({
  useOutlinePreview: (ws: string, body: unknown) => outline(ws, body),
  useDeckGeneration: () => ({ phase: "idle", stages: [], deck: null, file: { status: "idle" }, error: null, start: vi.fn(), cancel: vi.fn() }),
}));

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  window.history.replaceState(null, "", "/w/NORTHSTAR/insights/deck?s=price-ceiling,gone");
  outline.mockClear();
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const checkbox = (id: string) => host.querySelector<HTMLInputElement>(`input[id$="-${id}"]`);
const buttonNamed = (name: string) => [...host.querySelectorAll("button")].find((b) => b.textContent === name) as HTMLButtonElement;

describe("DeckBuilder", () => {
  it("preselects from the URL, flags unknown ids and keeps the URL in step with the picker", () => {
    const initial = parseDeckSelection(new URL(window.location.href).searchParams);
    act(() => root.render(<DeckBuilder ws="NORTHSTAR" initial={initial} />));

    expect(host.textContent).toContain("1 selected finding is no longer in this workspace");
    expect(checkbox("price-ceiling")?.checked).toBe(true);
    expect(checkbox("O2")).toBeNull(); // compact view: selected items only
    expect(outline.mock.lastCall?.[1]).toMatchObject({ title: "Strategic findings", signal_ids: ["price-ceiling"] });
    expect(host.textContent).toContain("Not included: Loyalty lapse — Its main claim no longer has verified support.");

    act(() => buttonNamed("Add more findings").click());
    act(() => checkbox("O2")!.click());
    act(() => checkbox("wtp")!.click());
    const url = new URL(window.location.href);
    expect(parseDeckSelection(url.searchParams)).toEqual({ signals: ["price-ceiling", "gone"], opportunities: ["O2"], analyses: ["wtp"] });
    expect(outline.mock.lastCall?.[1]).toMatchObject({ signal_ids: ["price-ceiling"], opportunity_ids: ["O2"], analysis_ids: ["wtp"] });
    expect(buttonNamed("Generate presentation").disabled).toBe(false);
  });

  it("teaches what to do with an empty selection", () => {
    act(() => root.render(<DeckBuilder ws="NORTHSTAR" initial={{ signals: [], opportunities: [], analyses: [] }} />));
    expect(host.textContent).toContain("Select findings from Insights, Growth Opportunities or Analytics to build a presentation.");
    expect(host.textContent).toContain("The outline appears once you select findings.");
    expect(buttonNamed("Generate presentation").disabled).toBe(true);
    act(() => buttonNamed("Choose findings here").click());
    expect(checkbox("O2")).not.toBeNull();
  });
});
