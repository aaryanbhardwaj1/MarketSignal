import { describe, expect, it } from "vitest";
import {
  bandLayout,
  bandPath,
  defaultFormat,
  histogram,
  linePath,
  linearScale,
  nearestIndex,
  niceDomain,
  niceStep,
  quantile,
  stackShares,
  ticks,
} from "./scale";

describe("linearScale", () => {
  it("maps domain to range, including inverted ranges", () => {
    const x = linearScale([0, 10], [0, 200]);
    expect(x(5)).toBe(100);
    const y = linearScale([0, 100], [120, 0]);
    expect(y(25)).toBe(90);
  });
  it("handles a zero-width domain", () => {
    expect(linearScale([3, 3], [10, 50])(3)).toBe(10);
  });
});

describe("niceStep / niceDomain / ticks", () => {
  it("chooses 1-2-2.5-5 steps", () => {
    expect(niceStep(100, 5)).toBe(20);
    expect(niceStep(1, 4)).toBe(0.25);
    expect(niceStep(0)).toBe(1);
  });
  it("expands to nice bounds and includes zero by default", () => {
    expect(niceDomain([12, 87])).toEqual([0, 100]);
    expect(niceDomain([12, 87], { includeZero: false })).toEqual([0, 100]);
    expect(niceDomain([52, 87], { includeZero: false })).toEqual([50, 90]);
    expect(niceDomain([-3, 7])).toEqual([-4, 8]);
    expect(niceDomain([])).toEqual([0, 1]);
    expect(niceDomain([0, 0])).toEqual([0, 1]);
  });
  it("produces clean ticks", () => {
    expect(ticks([0, 100], 5)).toEqual([0, 20, 40, 60, 80, 100]);
    expect(ticks([0, 0.3], 3)).toEqual([0, 0.1, 0.2, 0.3]);
  });
});

describe("bandLayout", () => {
  it("centres bands within equal steps", () => {
    const band = bandLayout(4, 400, 0.5);
    expect(band.step).toBe(100);
    expect(band.bandwidth).toBe(50);
    expect(band.start(0)).toBe(25);
    expect(band.start(3)).toBe(325);
  });
});

describe("stackShares", () => {
  it("returns shares and offsets summing to one", () => {
    const segs = stackShares([1, 3, 0, -2]);
    expect(segs.map((s) => s.share)).toEqual([0.25, 0.75, 0, 0]);
    expect(segs.map((s) => s.offset)).toEqual([0, 0.25, 1, 1]);
  });
  it("returns zero shares for an empty total", () => {
    expect(stackShares([0, 0]).every((s) => s.share === 0)).toBe(true);
  });
});

describe("quantile / histogram", () => {
  it("interpolates quantiles", () => {
    expect(quantile([1, 2, 3, 4], 0.5)).toBe(2.5);
    expect(quantile([5], 0.95)).toBe(5);
    expect(quantile([], 0.5)).toBeNaN();
  });
  it("bins values with a closed last bin", () => {
    const bins = histogram([0, 1, 2, 3, 4], 2);
    expect(bins.map((b) => b.count)).toEqual([2, 3]);
    expect(histogram([], 4)).toEqual([]);
    expect(histogram([7, 7, 7], 3).reduce((a, b) => a + b.count, 0)).toBe(3);
  });
});

describe("paths", () => {
  it("builds line and band paths", () => {
    expect(linePath([[0, 0], [10, 5.555]])).toBe("M0 0 L10 5.56");
    expect(linePath([])).toBe("");
    expect(bandPath([[0, 0], [10, 0]], [[0, 5], [10, 5]])).toBe("M0 0 L10 0 L10 5 L0 5 Z");
  });
  it("finds the nearest index", () => {
    expect(nearestIndex([0, 10, 20], 14)).toBe(1);
    expect(nearestIndex([], 3)).toBe(-1);
  });
});

describe("defaultFormat", () => {
  it("groups thousands and limits decimals", () => {
    expect(defaultFormat(12345.678)).toBe("12,345.7");
    expect(defaultFormat(1.234)).toBe("1.23");
    expect(defaultFormat(Number.NaN)).toBe("–");
  });
});
