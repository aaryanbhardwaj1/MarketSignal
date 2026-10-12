import { describe, expect, it } from "vitest";
import {
  formatBytes,
  formatCompact,
  formatMs,
  formatNumber,
  formatPercent,
  formatRelativeDate,
  formatUsd,
  humanize,
  truncateHash,
} from "./format";

describe("format", () => {
  it("returns '-' for missing or non-finite values instead of 0", () => {
    for (const fn of [formatNumber, formatPercent, formatUsd, formatMs, formatCompact, formatBytes]) {
      expect(fn(null)).toBe("-");
      expect(fn(undefined)).toBe("-");
      expect(fn(Number.NaN)).toBe("-");
    }
  });

  it("formats numbers with grouping and sensible decimals", () => {
    expect(formatNumber(12480)).toBe("12,480");
    expect(formatNumber(3.14159)).toBe("3.14");
    expect(formatNumber(0.8125, 3)).toBe("0.813");
    expect(formatCompact(1530)).toBe("1.5K");
  });

  it("formats percents from ratios by default, or from percent units", () => {
    expect(formatPercent(0.4236)).toBe("42.4%");
    expect(formatPercent(42.36, { ratio: false, digits: 0 })).toBe("42%");
  });

  it("formats USD, keeping sub-cent precision for estimates", () => {
    expect(formatUsd(1234.5)).toBe("$1,234.50");
    expect(formatUsd(0.0042)).toBe("$0.0042");
    expect(formatUsd(0)).toBe("$0.00");
  });

  it("keeps the existing ms, bytes, hash and humanize behaviour", () => {
    expect(formatMs(840)).toBe("840 ms");
    expect(formatMs(1234)).toBe("1.23 s");
    expect(formatMs(12_345)).toBe("12.3 s");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(truncateHash("abcdef0123456789")).toBe("abcdef012345...");
    expect(humanize("ready_degraded")).toBe("ready degraded");
  });

  it("formats relative dates against an injectable clock", () => {
    const now = new Date("2026-10-12T12:00:00Z");
    expect(formatRelativeDate("2026-10-12T11:59:30Z", now)).toBe("just now");
    expect(formatRelativeDate("2026-10-12T09:00:00Z", now)).toBe("3 hours ago");
    expect(formatRelativeDate("2026-10-11T12:00:00Z", now)).toBe("yesterday");
    expect(formatRelativeDate("2026-09-28T12:00:00Z", now)).toBe("2 weeks ago");
    expect(formatRelativeDate(null, now)).toBe("-");
    expect(formatRelativeDate("not a date", now)).toBe("not a date");
  });
});
