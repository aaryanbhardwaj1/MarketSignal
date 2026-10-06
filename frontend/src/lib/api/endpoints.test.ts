import { describe, expect, it } from "vitest";
import { runStreamUrl } from "./endpoints";

describe("runStreamUrl", () => {
  it("prefixes an API stream path with the API origin", () => {
    expect(runStreamUrl("/api/workspaces/NORTHSTAR/runs/r1/events?st=tok", "http://api:8000")).toBe(
      "http://api:8000/api/workspaces/NORTHSTAR/runs/r1/events?st=tok",
    );
  });

  it.each([
    "https://evil.example/api/x",
    "//evil.example/api/x",
    "api/workspaces/x",
    "/api/x\\@evil",
    "/api/x y",
    "",
  ])("rejects %j", (path) => {
    expect(runStreamUrl(path, "http://api:8000")).toBeNull();
  });
});
