import { describe, expect, it } from "vitest";
import { SIDEBAR_STORAGE_KEY, readSidebarCollapsed, writeSidebarCollapsed } from "./sidebar-state";

function memoryStorage() {
  const map = new Map<string, string>();
  return {
    map,
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
  };
}

const throwing = {
  getItem: () => {
    throw new Error("SecurityError");
  },
  setItem: () => {
    throw new Error("QuotaExceededError");
  },
};

describe("sidebar collapse persistence", () => {
  it("round-trips the collapsed state", () => {
    const storage = memoryStorage();
    expect(readSidebarCollapsed(storage)).toBe(false);
    writeSidebarCollapsed(true, storage);
    expect(storage.map.get(SIDEBAR_STORAGE_KEY)).toBe("1");
    expect(readSidebarCollapsed(storage)).toBe(true);
    writeSidebarCollapsed(false, storage);
    expect(readSidebarCollapsed(storage)).toBe(false);
  });

  it("ignores unexpected stored values", () => {
    const storage = memoryStorage();
    storage.map.set(SIDEBAR_STORAGE_KEY, "true");
    expect(readSidebarCollapsed(storage)).toBe(false);
  });

  it("never throws when storage is unavailable", () => {
    expect(readSidebarCollapsed(throwing)).toBe(false);
    expect(() => writeSidebarCollapsed(true, throwing)).not.toThrow();
    expect(readSidebarCollapsed(null)).toBe(false);
  });
});
