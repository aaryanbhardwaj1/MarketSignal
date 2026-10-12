import { afterEach, describe, expect, it, vi } from "vitest";
import catalogFixture from "../__fixtures__/evaluation-catalog.json";
import itemsFixture from "../__fixtures__/evaluation-items-p3-grounded-live.json";
import type { EvalCatalog, EvalItemsPage, EvalMetric } from "../contracts";
import { getEvalItems } from "./evaluation";

// Captured payloads (JSON imports widen literal unions, so enum values are checked in the
// backend unit tests; here they are used through the contract types).
const catalog = catalogFixture as unknown as EvalCatalog;
const items = itemsFixture as unknown as EvalItemsPage;

function metrics(node: unknown, out: EvalMetric[] = []): EvalMetric[] {
  if (Array.isArray(node)) node.forEach((n) => metrics(n, out));
  else if (node && typeof node === "object") {
    const o = node as Record<string, unknown>;
    if ("id" in o && "value" in o && "unit" in o && "source" in o) out.push(o as unknown as EvalMetric);
    else Object.values(o).forEach((v) => metrics(v, out));
  }
  return out;
}

describe("evaluation fixtures", () => {
  it("carries a source on every metric and the always-on caveats", () => {
    const all = metrics(catalog);
    expect(all.length).toBeGreaterThan(100);
    for (const m of all) {
      expect(m.value === null || typeof m.value === "number").toBe(true);
      expect(m.source.path.startsWith("/")).toBe(false);
    }
    const caveats = catalog.caveats.map((c) => c.id);
    expect(caveats).toEqual(expect.arrayContaining(["small-test-n", "a3-not-run", "p5-holdout-routing"]));
  });

  it("has the first ten grounded items", () => {
    expect(items.run_id).toBe("p3-grounded-live");
    expect(items.items).toHaveLength(10);
    expect(items.items.every((i) => i.phase === "grounded")).toBe(true);
  });
});

describe("getEvalItems", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("clamps the page size and passes the bucket", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(items), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await getEvalItems("p3-grounded-live", { offset: 10, limit: 500, bucket: "mixed" });
    const url = String((fetchMock.mock.calls[0] as unknown[])[0]);
    expect(url).toContain("/api/dev/eval/runs/p3-grounded-live/items?");
    expect(url).toContain("limit=50");
    expect(url).toContain("offset=10");
    expect(url).toContain("bucket=mixed");
  });
});
