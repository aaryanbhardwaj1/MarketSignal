import { describe, expect, it } from "vitest";
import {
  ApiError,
  describeError,
  parseApiError,
  UNKNOWN_ERROR,
  VALIDATION_ERROR,
} from "./errors";

describe("parseApiError", () => {
  it("parses the standard error envelope", () => {
    const err = parseApiError(404, {
      error: { code: "WORKSPACE_NOT_FOUND", message: "workspace not found" },
    });
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toBeInstanceOf(Error);
    expect(err.status).toBe(404);
    expect(err.code).toBe("WORKSPACE_NOT_FOUND");
    expect(err.message).toBe("workspace not found");
  });

  it("keeps extra envelope fields such as the 410 tombstone", () => {
    const tombstone = {
      handle: "NORTHSTAR/X@v1:P1",
      source_code: "X",
      title: "Deleted doc",
      version: 1,
      deleted_at: "2026-10-05T00:00:00Z",
    };
    const err = parseApiError(410, {
      error: { code: "SOURCE_DELETED", message: "source deleted", tombstone },
    });
    expect(err.code).toBe("SOURCE_DELETED");
    expect(err.details.tombstone).toEqual(tombstone);
  });

  it("normalises FastAPI validation errors (detail array)", () => {
    const err = parseApiError(422, {
      detail: [
        { loc: ["body", "code"], msg: "String should match pattern", type: "string_pattern_mismatch" },
        { loc: ["query", "q"], msg: "too short" },
      ],
    });
    expect(err.code).toBe(VALIDATION_ERROR);
    expect(err.message).toBe("code: String should match pattern; query.q: too short");
  });

  it("handles a string detail and non-422 detail", () => {
    const err = parseApiError(404, { detail: "Not Found" });
    expect(err.code).toBe(UNKNOWN_ERROR);
    expect(err.message).toBe("Not Found");
  });

  it("falls back gracefully for empty or non-JSON bodies", () => {
    const err = parseApiError(502, null, "Bad Gateway");
    expect(err.code).toBe(UNKNOWN_ERROR);
    expect(err.message).toBe("Request failed (502 Bad Gateway)");
  });

  it("tolerates malformed envelopes", () => {
    const err = parseApiError(500, { error: { code: 42 } });
    expect(err.code).toBe(UNKNOWN_ERROR);
    expect(err.message).toBe("Request failed (500)");
  });
});

describe("describeError", () => {
  it("describes ApiError, Error and unknown values", () => {
    expect(describeError(new ApiError(409, "WORKSPACE_EXISTS", "taken"))).toEqual({
      code: "WORKSPACE_EXISTS",
      message: "taken",
    });
    expect(describeError(new Error("boom"))).toEqual({ code: UNKNOWN_ERROR, message: "boom" });
    expect(describeError("x")).toEqual({ code: UNKNOWN_ERROR, message: "x" });
  });
});
