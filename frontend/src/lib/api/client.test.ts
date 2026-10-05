import { afterEach, describe, expect, it, vi } from "vitest";
import { apiRequest, buildUrl } from "./client";
import { ApiError, NETWORK_ERROR } from "./errors";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("buildUrl", () => {
  it("drops empty query values", () => {
    expect(buildUrl("/api/x", { q: "gen z", mode: "lexical", child_id: null, k: undefined })).toBe(
      "http://localhost:8000/api/x?q=gen+z&mode=lexical",
    );
    expect(buildUrl("/api/x", {})).toBe("http://localhost:8000/api/x");
  });
});

describe("apiRequest", () => {
  it("returns status and parsed JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ created: false }), { status: 200 })),
    );
    await expect(apiRequest("/api/x")).resolves.toEqual({ status: 200, data: { created: false } });
  });

  it("throws an ApiError carrying the envelope code", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ error: { code: "UNSUPPORTED_TYPE", message: "nope" } }), {
            status: 415,
          }),
      ),
    );
    await expect(apiRequest("/api/x")).rejects.toMatchObject({
      status: 415,
      code: "UNSUPPORTED_TYPE",
      message: "nope",
    });
  });

  it("maps transport failures to NETWORK_ERROR", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    const err = await apiRequest("/api/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe(NETWORK_ERROR);
  });
});
