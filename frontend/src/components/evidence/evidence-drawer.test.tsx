// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Evidence } from "@/lib/api/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const nav = vi.hoisted(() => {
  let search = "";
  const listeners = new Set<() => void>();
  const set = (href: string) => {
    const i = href.indexOf("?");
    search = i >= 0 ? href.slice(i) : "";
    window.history.replaceState(null, "", href);
    listeners.forEach((l) => l());
  };
  return {
    calls: [] as string[],
    set,
    reset: () => set("/w/NORTHSTAR/evidence"),
    getSearch: () => search,
    subscribe: (l: () => void) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
  };
});

vi.mock("next/navigation", async () => {
  const { useSyncExternalStore } = await import("react");
  const router = {
    push: (href: string) => {
      nav.calls.push(`push ${href}`);
      nav.set(href);
    },
    replace: (href: string) => {
      nav.calls.push(`replace ${href}`);
      nav.set(href);
    },
  };
  return {
    usePathname: () => "/w/NORTHSTAR/evidence",
    useRouter: () => router,
    useSearchParams: () => new URLSearchParams(useSyncExternalStore(nav.subscribe, nav.getSearch, nav.getSearch)),
  };
});

const getEvidence = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/endpoints", () => ({ getEvidence, getResult: vi.fn(() => new Promise(() => {})) }));

import { EvidencePassageView } from "./evidence-drawer";
import { EvidenceDrawerProvider, useEvidenceDrawer } from "./evidence-drawer-provider";

const HANDLE = "NORTHSTAR/BRAND-STRATEGY@v1:P4.B2";
const CHILD = "0b6f2a52-3c1d-4e8f-9a7b-1c2d3e4f5a6b";
const TEXT = "Gen Z shoppers compare prices on mobile. Delivery speed decides the basket. Loyalty follows.";
const start = TEXT.indexOf("Delivery speed");
const end = start + "Delivery speed decides the basket.".length;

const EVIDENCE: Evidence = {
  handle: HANDLE,
  text: TEXT,
  content_hash: "sha256-abc123",
  locator: { page: 4, block: 2 },
  locator_label: "Page 4, block 2",
  heading_path: ["Brand strategy", "Audience"],
  source: {
    source_id: "5e0c1c7a-0000-4000-8000-000000000001",
    source_code: "BRAND-STRATEGY",
    title: "Brand Strategy 2026",
    source_type: "pdf",
    source_class: "internal",
    confidentiality: "confidential" as Evidence["source"]["confidentiality"],
    version: 1,
    version_status: "ready" as Evidence["source"]["version_status"],
    latest_version: 1,
    is_latest: true,
    original_filename: null,
    mime_type: null,
    ingested_at: null,
  },
  provenance: {
    source_content_sha256: null,
    parent_content_sha256: null,
    parser_version: "p1",
    structure_version: null,
    chunking_policy_version: null,
    embedding_model: null,
  },
  context: { previous_excerpt: "Earlier passage.", next_excerpt: "Later passage." },
  children: [
    { child_id: CHILD, ordinal: 1, kind: "sentence", char_start: start, char_end: end },
    { child_id: "1b6f2a52-3c1d-4e8f-9a7b-1c2d3e4f5a6b", ordinal: 0, kind: "sentence", char_start: 0, char_end: start - 1 },
  ],
  highlight: { child_id: CHILD, char_start: start, char_end: end, text: TEXT.slice(start, end) },
};

let host: HTMLDivElement;
let root: Root;

function withClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

/** Text outside every <details> disclosure. */
function visibleText(el: HTMLElement): string {
  const clone = el.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("details").forEach((d) => d.remove());
  return clone.textContent ?? "";
}

beforeEach(() => {
  nav.reset();
  nav.calls.length = 0;
  getEvidence.mockReset();
  getEvidence.mockResolvedValue(EVIDENCE);
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

describe("EvidencePassageView", () => {
  it("shows a spreadsheet or CSV row as labelled fields, marking the cited field", () => {
    const row = "reason: Fit - runs small; total_sku_returns: 1421; share_of_sku_returns_pct: 41";
    const csv: Evidence = {
      ...EVIDENCE,
      text: row,
      locator_label: "Row 43",
      source: { ...EVIDENCE.source, source_type: "csv" as Evidence["source"]["source_type"] },
      children: [],
    };
    act(() =>
      root.render(
        withClient(<EvidencePassageView ws="NORTHSTAR" evidence={csv} span={{ childId: "", charStart: 8, charEnd: 24, expectedText: null }} />),
      ),
    );
    const visible = visibleText(host);
    expect(visible).toContain("Total SKU returns");
    expect(visible).toContain("1,421");
    expect(visible).toContain("41%");
    expect(visible).not.toContain("total_sku_returns");
    expect(host.querySelector("dd.evidence-mark")?.textContent).toContain("Fit - runs small");
  });

  it("highlights the cited span and keeps the handle inside Technical details only", () => {
    act(() =>
      root.render(
        withClient(
          <EvidencePassageView
            ws="NORTHSTAR"
            evidence={EVIDENCE}
            span={{ childId: CHILD, charStart: start, charEnd: end, expectedText: TEXT.slice(start, end) }}
            onSelectChild={() => {}}
          />,
        ),
      ),
    );
    const mark = host.querySelector("mark.evidence-mark");
    expect(mark?.textContent).toContain("Delivery speed decides the basket.");
    expect(host.querySelector("#evidence-passage-label")?.textContent).toBe("Page 4");
    expect(host.textContent).toContain("Internal");

    const visible = visibleText(host);
    expect(visible).not.toContain("block 2");
    // Provenance states the version in plain words; ids stay in Technical details.
    expect(visible).toContain("Version 1");
    expect(visible).toContain("Current version");
    expect(visible).toContain("Brand Strategy 2026");
    for (const technical of [HANDLE, CHILD, "sha256-abc123", "BRAND-STRATEGY"]) {
      expect(visible).not.toContain(technical);
    }
    const details = Array.from(host.querySelectorAll("details")).find((d) => d.textContent?.includes("Technical details"));
    expect(details?.textContent).toContain(HANDLE);
    expect(details?.textContent).toContain(CHILD);
    expect(details?.textContent).toContain("sha256-abc123");
  });

  it("shows a superseded notice for older versions", () => {
    const old = { ...EVIDENCE, source: { ...EVIDENCE.source, is_latest: false, latest_version: 2, version_status: "superseded" as Evidence["source"]["version_status"] } };
    getEvidence.mockReturnValue(new Promise(() => {}));
    act(() => root.render(withClient(<EvidencePassageView ws="NORTHSTAR" evidence={old} span={null} />)));
    expect(host.textContent).toContain("Superseded: this passage is from version 1; version 2 is current");
    expect(host.textContent).toContain("Earlier version of this source");
  });
});

function Opener() {
  const drawer = useEvidenceDrawer();
  return (
    <>
      <button type="button" id="open-ev" onClick={() => drawer.openEvidence({ handle: HANDLE, childId: CHILD })}>
        Open evidence
      </button>
      <button type="button" id="open-res" onClick={() => drawer.openResult("r-1")}>
        Open result
      </button>
    </>
  );
}

/** Polls (inside act) until the condition holds; robust under a loaded test runner. */
async function waitFor(condition: () => boolean, timeoutMs = 3000) {
  const deadline = Date.now() + timeoutMs;
  while (!condition()) {
    if (Date.now() > deadline) throw new Error("waitFor timed out");
    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });
  }
}

const dialog = () => host.querySelector("dialog")!;

describe("EvidenceDrawerProvider", () => {
  it("opens from a citation, syncs ?ev=&child=, closes on Esc and returns focus", async () => {
    act(() => root.render(withClient(<EvidenceDrawerProvider ws="NORTHSTAR"><Opener /></EvidenceDrawerProvider>)));
    expect(dialog().hasAttribute("open")).toBe(false);

    const opener = host.querySelector<HTMLButtonElement>("#open-ev")!;
    opener.focus();
    act(() => opener.click());
    await waitFor(() => Boolean(dialog().querySelector("mark")));

    const url = new URL(nav.calls[0].replace("push ", ""), "http://x");
    expect(url.searchParams.get("ev")).toBe(HANDLE);
    expect(url.searchParams.get("child")).toBe(CHILD);
    expect(dialog().hasAttribute("open")).toBe(true);
    expect(getEvidence).toHaveBeenCalledWith("NORTHSTAR", HANDLE, CHILD, expect.anything());
    expect(dialog().textContent).toContain("Evidence passage");
    expect(dialog().textContent).toContain("Brand Strategy 2026");
    expect(dialog().querySelector("mark")?.textContent).toContain("Delivery speed");

    act(() => {
      dialog().dispatchEvent(new Event("cancel", { cancelable: true }));
    });
    expect(dialog().hasAttribute("open")).toBe(false);
    expect(nav.getSearch()).toBe("");
    expect(document.activeElement).toBe(opener);
  });

  it("opens on load from the legacy ?h= deep link", async () => {
    nav.set(`/w/NORTHSTAR/evidence?h=${encodeURIComponent(HANDLE)}`);
    act(() => root.render(withClient(<EvidenceDrawerProvider ws="NORTHSTAR"><p>page</p></EvidenceDrawerProvider>)));
    await waitFor(() => getEvidence.mock.calls.length > 0);
    expect(dialog().hasAttribute("open")).toBe(true);
    expect(getEvidence).toHaveBeenCalledWith("NORTHSTAR", HANDLE, null, expect.anything());
  });

  it("shows Evidence not found for an unknown handle", async () => {
    const { ApiError } = await import("@/lib/api/errors");
    getEvidence.mockRejectedValue(new ApiError(404, "EVIDENCE_NOT_FOUND", "nope"));
    nav.set(`/w/NORTHSTAR/evidence?ev=${encodeURIComponent(HANDLE)}`);
    act(() => root.render(withClient(<EvidenceDrawerProvider ws="NORTHSTAR"><p>page</p></EvidenceDrawerProvider>)));
    await waitFor(() => visibleText(dialog()).includes("Evidence not found"));
    expect(visibleText(dialog())).not.toContain(HANDLE);
  });

  it("opens a computed result with ?res=", async () => {
    act(() => root.render(withClient(<EvidenceDrawerProvider ws="NORTHSTAR"><Opener /></EvidenceDrawerProvider>)));
    act(() => host.querySelector<HTMLButtonElement>("#open-res")!.click());
    await waitFor(() => dialog().hasAttribute("open"));
    expect(nav.getSearch()).toBe("?res=r-1");
    expect(dialog().hasAttribute("open")).toBe(true);
    expect(dialog().textContent).toContain("Computed result");
  });
});
