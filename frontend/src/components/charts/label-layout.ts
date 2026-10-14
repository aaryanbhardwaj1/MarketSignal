/**
 * Pure text-layout helpers for SVG chart labels (SVG text does not wrap). Widths are estimated
 * from character counts, so the result is deterministic on the server and in tests; the estimate
 * errs wide so labels that "fit" really fit.
 */

const ELLIPSIS = "…";

/** Approximate rendered width of `text` at `fontSize` px in the UI sans-serif. */
export function estimateTextWidth(text: string, fontSize = 11): number {
  let units = 0;
  for (const ch of text) {
    if (/[ilj.,:;'|!]/.test(ch)) units += 0.3;
    else if (ch === " ") units += 0.3;
    else if (/[mwMW@%&]/.test(ch)) units += 0.85;
    else if (/[A-Z0-9]/.test(ch)) units += 0.64;
    else units += 0.55;
  }
  return units * fontSize;
}

/** Longest prefix of `text` that fits `maxWidth` with a trailing ellipsis. */
export function truncateToWidth(text: string, maxWidth: number, fontSize = 11): string {
  if (estimateTextWidth(text, fontSize) <= maxWidth) return text;
  const chars = [...text];
  for (let n = chars.length - 1; n > 0; n -= 1) {
    const candidate = chars.slice(0, n).join("").trimEnd() + ELLIPSIS;
    if (estimateTextWidth(candidate, fontSize) <= maxWidth) return candidate;
  }
  return ELLIPSIS;
}

export interface WrappedLabel {
  lines: string[];
  /** True when part of the text was cut; callers should expose the full text (e.g. `<title>`). */
  truncated: boolean;
}

/**
 * Word-aware wrap of `text` into at most `maxLines` lines no wider than `maxWidth`. Overflow on
 * the last line (or a single word longer than a line) is truncated with an ellipsis.
 */
export function wrapLabel(text: string, maxWidth: number, { maxLines = 2, fontSize = 11 } = {}): WrappedLabel {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return { lines: [], truncated: false };
  const fits = (s: string) => estimateTextWidth(s, fontSize) <= maxWidth;
  const lines: string[] = [];
  let current = "";
  let i = 0;
  while (i < words.length && lines.length < maxLines - 1) {
    const next = current ? `${current} ${words[i]}` : words[i];
    if (fits(next)) {
      current = next;
      i += 1;
    } else if (current) {
      lines.push(current);
      current = "";
    } else {
      break; // a single word wider than a line goes to the last line, truncated
    }
  }
  const rest = [current, ...words.slice(i)].filter(Boolean).join(" ");
  const last = truncateToWidth(rest, maxWidth, fontSize);
  if (last) lines.push(last);
  return { lines, truncated: lines.join(" ") !== words.join(" ") };
}

export interface PlacedLabel {
  /** Anchor x of the label. */
  x: number;
  /** Baseline y of the label. */
  y: number;
  text: string;
  anchor?: "start" | "middle" | "end";
}

/**
 * Which labels can be drawn without overlapping an earlier drawn label (greedy, in the given
 * order). Two labels collide when their estimated boxes overlap horizontally (plus `gap`) and
 * their baselines are closer than one line. Empty labels are never drawn. Hidden labels stay available in the data table.
 */
export function visibleLabels(labels: readonly PlacedLabel[], { fontSize = 11, gap = 3 } = {}): boolean[] {
  const drawn: { x0: number; x1: number; y: number }[] = [];
  return labels.map((l) => {
    if (!l.text) return false;
    const w = estimateTextWidth(l.text, fontSize);
    const x0 = l.anchor === "start" ? l.x : l.anchor === "end" ? l.x - w : l.x - w / 2;
    const box = { x0, x1: x0 + w, y: l.y };
    const clash = drawn.some((d) => box.x0 < d.x1 + gap && d.x0 < box.x1 + gap && Math.abs(d.y - box.y) < fontSize + 2);
    if (clash) return false;
    drawn.push(box);
    return true;
  });
}
