import { describe, expect, it } from "vitest";
import { validateSourceCode, validateUploadFile, validateWorkspaceCode } from "./validation";

describe("validateWorkspaceCode", () => {
  it("accepts API-valid codes and rejects others", () => {
    expect(validateWorkspaceCode("NORTHSTAR")).toBeNull();
    expect(validateWorkspaceCode("A1")).toBeNull();
    expect(validateWorkspaceCode("")).not.toBeNull();
    expect(validateWorkspaceCode("bad")).not.toBeNull();
    expect(validateWorkspaceCode("1ABC")).not.toBeNull();
    expect(validateWorkspaceCode("A")).not.toBeNull();
    expect(validateWorkspaceCode("A".repeat(17))).not.toBeNull();
  });
});

describe("validateSourceCode", () => {
  it("treats empty as optional and enforces the pattern", () => {
    expect(validateSourceCode("")).toBeNull();
    expect(validateSourceCode("Q3-REVIEW")).toBeNull();
    expect(validateSourceCode("survey")).not.toBeNull();
    expect(validateSourceCode("A--B")).not.toBeNull();
  });
});

describe("validateUploadFile", () => {
  it("checks presence, extension and size", () => {
    expect(validateUploadFile(null)).not.toBeNull();
    expect(validateUploadFile(new File(["x"], "notes.TXT"))).toBeNull();
    expect(validateUploadFile(new File(["x"], "virus.exe"))).toMatch(/Unsupported/);
  });
});
