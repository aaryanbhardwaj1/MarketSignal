import { afterEach, describe, expect, it, vi } from "vitest";
import catalogFixture from "../__fixtures__/evaluation-catalog.json";
import type { EvalCatalog, RagasItemsPage } from "../contracts";
import { getRagasItems } from "./evaluation";

const catalog = catalogFixture as unknown as EvalCatalog;

describe("RAGAS catalog section (E13)", () => {
  it("lists both runs and never shows numbers for metrics that were not run", () => {
    const ragas = catalog.ragas;
    expect(ragas?.runs.map((r) => r.id)).toEqual(["ragas-p3-live-v0", "ragas-p4-research-test"]);
    const metrics = (ragas?.runs ?? []).flatMap((r) => r.configurations.flatMap((c) => c.metrics));
    expect(metrics.length).toBeGreaterThan(0);
    for (const m of metrics) {
      expect(m.source.pointer.startsWith("/runs/")).toBe(true);
      if (m.status === "not_run") expect(m.summary).toBeNull();
      else expect(typeof m.summary.mean).toBe("number");
    }
    const llm = new Set(ragas?.definitions.filter((d) => d.needs_llm).map((d) => d.key));
    expect(metrics.filter((m) => llm.has(m.key)).every((m) => m.status === "not_run")).toBe(true);
  });
});

describe("getRagasItems", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("passes the configuration as the bucket filter and clamps the page size", async () => {
    const page: RagasItemsPage = { run_id: "ragas-p4-research-test", total: 0, items: [] };
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(page), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const got = await getRagasItems("ragas-p4-research-test", { limit: 500, configuration: "research" });
    expect(got.run_id).toBe("ragas-p4-research-test");
    const url = String((fetchMock.mock.calls[0] as unknown[])[0]);
    expect(url).toContain("/api/dev/eval/runs/ragas-p4-research-test/items?");
    expect(url).toContain("limit=50");
    expect(url).toContain("bucket=research");
  });

  it("omits the bucket when no configuration is chosen", async () => {
    const page: RagasItemsPage = { run_id: "ragas-p3-live-v0", total: 0, items: [] };
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(page), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await getRagasItems("ragas-p3-live-v0");
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).not.toContain("bucket=");
  });
});
