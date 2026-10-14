/**
 * Pure scale and layout helpers for the hand-rolled SVG charts. No DOM, no React: every
 * function here is unit-tested in `scale.test.ts`.
 */

export type Domain = readonly [number, number];

export interface LinearScale {
  (value: number): number;
  domain: Domain;
  range: Domain;
}

/** Maps `domain` linearly onto `range`; a zero-width domain maps everything to the range start. */
export function linearScale(domain: Domain, range: Domain): LinearScale {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0;
  const fn = ((value: number) => (span === 0 ? r0 : r0 + ((value - d0) / span) * (r1 - r0))) as LinearScale;
  fn.domain = domain;
  fn.range = range;
  return fn;
}

/** A "nice" step (1, 2, 2.5 or 5 x 10^n) giving about `count` intervals over `span`. */
export function niceStep(span: number, count = 5): number {
  if (!(span > 0) || !Number.isFinite(span)) return 1;
  const raw = span / Math.max(1, count);
  const power = 10 ** Math.floor(Math.log10(raw));
  const fraction = raw / power;
  const nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
  return nice * power;
}

/** Rounds to the precision of `step`, removing float noise such as 0.30000000000000004. */
function clean(value: number, step: number): number {
  const decimals = Math.max(0, -Math.floor(Math.log10(step)) + 1);
  return Number(value.toFixed(decimals));
}

/** Domain expanded outward to nice steps; includes zero unless `includeZero` is false. */
export function niceDomain(values: readonly number[], { includeZero = true, count = 5 } = {}): Domain {
  const finite = values.filter(Number.isFinite);
  if (finite.length === 0) return [0, 1];
  let min = Math.min(...finite);
  let max = Math.max(...finite);
  if (includeZero) {
    min = Math.min(0, min);
    max = Math.max(0, max);
  }
  if (min === max) {
    const pad = min === 0 ? 1 : Math.abs(min) * 0.1;
    min -= includeZero && min >= 0 ? 0 : pad;
    max += pad;
  }
  const step = niceStep(max - min, count);
  return [clean(Math.floor(min / step) * step, step), clean(Math.ceil(max / step) * step, step)];
}

/** Evenly spaced tick values covering `domain` at a nice step. */
export function ticks(domain: Domain, count = 5): number[] {
  const [d0, d1] = domain;
  if (d1 <= d0) return [d0];
  const step = niceStep(d1 - d0, count);
  const out: number[] = [];
  for (let v = Math.ceil(d0 / step) * step; v <= d1 + step * 1e-9; v += step) out.push(clean(v, step));
  return out;
}

export interface Band {
  /** Start offset of band `i`. */
  start: (i: number) => number;
  bandwidth: number;
  step: number;
}

/** Splits `length` into `n` bands with `padding` (0-1, fraction of the step) between them. */
export function bandLayout(n: number, length: number, padding = 0.3): Band {
  const count = Math.max(1, n);
  const step = length / count;
  const bandwidth = step * (1 - Math.min(Math.max(padding, 0), 0.9));
  const inset = (step - bandwidth) / 2;
  return { step, bandwidth, start: (i) => i * step + inset };
}

export interface Segment {
  value: number;
  /** Share of the total, 0-1. */
  share: number;
  /** Cumulative share before this segment, 0-1. */
  offset: number;
}

/** 100% composition. Negative and non-finite values count as zero; an all-zero total gives zero shares. */
export function stackShares(values: readonly number[]): Segment[] {
  const safe = values.map((v) => (Number.isFinite(v) && v > 0 ? v : 0));
  const total = safe.reduce((a, b) => a + b, 0);
  let offset = 0;
  return safe.map((value) => {
    const share = total === 0 ? 0 : value / total;
    const seg = { value, share, offset };
    offset += share;
    return seg;
  });
}

/** Linear-interpolated quantile (p in 0-1) of the values; NaN for an empty list. */
export function quantile(values: readonly number[], p: number): number {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (sorted.length === 0) return Number.NaN;
  const pos = (sorted.length - 1) * Math.min(Math.max(p, 0), 1);
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

export interface Bin {
  x0: number;
  x1: number;
  count: number;
}

/** Equal-width histogram over the value range; the last bin is closed on the right. */
export function histogram(values: readonly number[], binCount = 12): Bin[] {
  const finite = values.filter(Number.isFinite);
  if (finite.length === 0) return [];
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const n = Math.max(1, Math.floor(binCount));
  const width = max === min ? 1 : (max - min) / n;
  const bins: Bin[] = Array.from({ length: n }, (_, i) => ({ x0: min + i * width, x1: min + (i + 1) * width, count: 0 }));
  for (const v of finite) bins[Math.min(n - 1, Math.floor((v - min) / width))].count += 1;
  return bins;
}

export type Point = readonly [number, number];

/** SVG path through the points (straight segments). Empty string for no points. */
export function linePath(points: readonly Point[]): string {
  return points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${round(x)} ${round(y)}`).join(" ");
}

/** Closed SVG path between an upper and a lower line (same x positions), for intervals/bands. */
export function bandPath(upper: readonly Point[], lower: readonly Point[]): string {
  if (upper.length === 0 || lower.length === 0) return "";
  return `${linePath(upper)} ${[...lower].reverse().map(([x, y]) => `L${round(x)} ${round(y)}`).join(" ")} Z`;
}

/** Index of the point whose x is nearest to `x` (points sorted by x); -1 for none. */
export function nearestIndex(xs: readonly number[], x: number): number {
  let best = -1;
  let dist = Number.POSITIVE_INFINITY;
  xs.forEach((v, i) => {
    const d = Math.abs(v - x);
    if (d < dist) {
      dist = d;
      best = i;
    }
  });
  return best;
}

function round(n: number): number {
  return Math.round(n * 100) / 100;
}

/** Default number formatter for labels: grouped thousands, up to 2 decimals. */
export function defaultFormat(value: number): string {
  if (!Number.isFinite(value)) return "–";
  return value.toLocaleString("en-US", { maximumFractionDigits: Math.abs(value) < 10 ? 2 : 1 });
}
