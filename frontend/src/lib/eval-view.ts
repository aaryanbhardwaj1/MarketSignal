/**
 * View helpers for the RAG Evaluation pages (Developer Tools). Pure functions only: every number
 * shown comes from an `EvalMetric` in the precomputed catalog; nothing here invents a figure.
 */
import type { StatusTone } from "@/components/ui/tone";
import type {
  EvalCatalog,
  EvalMetric,
  EvalProvenance,
  EvalRunId,
  EvalSource,
  MetricUnit,
} from "@/lib/api/contracts";
import { ApiError } from "@/lib/api/errors";
import { formatMs, formatNumber, formatUsd } from "@/lib/format";

export const MINUS = "−";
const EMPTY = "-";

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Value in its unit. Ratios keep three decimals so 1.000 and 0.873 line up in tables. */
export function formatEvalValue(value: number | null | undefined, unit: MetricUnit): string {
  if (!isNum(value)) return EMPTY;
  switch (unit) {
    case "ratio":
      return value.toFixed(3);
    case "percent":
      return `${value.toFixed(1)}%`;
    case "ms":
      return formatMs(value);
    case "s":
      return `${formatNumber(value, 2)} s`;
    case "usd":
      // Per-run costs are cents; keep four decimals so $0.0135 does not collapse to $0.01.
      return formatUsd(value, { digits: Math.abs(value) < 10 ? 4 : 2 });
    case "tokens":
      return formatNumber(value, 0);
    case "count":
      return formatNumber(value, Number.isInteger(value) ? 0 : 2);
  }
}

/** Signed value with an explicit "+" or a true minus sign ("−0.167"). Zero has no sign. */
export function formatSigned(value: number | null | undefined, unit: MetricUnit): string {
  if (!isNum(value)) return EMPTY;
  const body = formatEvalValue(Math.abs(value), unit);
  if (value > 0) return `+${body}`;
  if (value < 0) return `${MINUS}${body}`;
  return body;
}

export function ciOf(m: Pick<EvalMetric, "ci_low" | "ci_high">): [number, number] | null {
  return isNum(m.ci_low) && isNum(m.ci_high) ? [m.ci_low, m.ci_high] : null;
}

/** "95% CI 0.725 to 1.000"; signed bounds for deltas. */
export function formatCi(m: EvalMetric, { signed = false }: { signed?: boolean } = {}): string | null {
  const ci = ciOf(m);
  if (!ci) return null;
  const f = signed ? formatSigned : formatEvalValue;
  return `95% CI ${f(ci[0], m.unit)} to ${f(ci[1], m.unit)}`;
}

/** "k / n" when both are present, else "n = …" when only n is. */
export function formatCountOf(m: Pick<EvalMetric, "k" | "n">): string | null {
  if (isNum(m.k) && isNum(m.n)) return `${formatNumber(m.k)} / ${formatNumber(m.n)}`;
  if (isNum(m.n)) return `n = ${formatNumber(m.n)}`;
  return null;
}

/** A count that is itself "k of n" reads best as "9 / 9" rather than "9" plus a second line. */
export function isKOfN(m: Pick<EvalMetric, "value" | "k" | "n" | "unit">): boolean {
  return m.unit === "count" && isNum(m.k) && isNum(m.n) && m.value === m.k;
}

/** Main display for a metric value. */
export function primaryDisplay(m: Pick<EvalMetric, "value" | "k" | "n" | "unit">): string {
  return isKOfN(m) ? `${formatNumber(m.k)} / ${formatNumber(m.n)}` : formatEvalValue(m.value, m.unit);
}

export type Direction = "higher" | "lower";

export interface DeltaVerdict {
  label: string;
  tone: StatusTone;
  distinguishable: boolean;
}

/**
 * Reads a paired delta. A CI that includes 0 is "Not distinguishable" whatever the point estimate.
 * Otherwise the sign is judged against the measure's better direction; a change in the bad
 * direction is a warning. Resource measures ("lower" is better) read as "Costs more/less".
 */
export function deltaVerdict(
  m: Pick<EvalMetric, "value" | "ci_low" | "ci_high">,
  direction: Direction = "higher",
  { resource = false }: { resource?: boolean } = {},
): DeltaVerdict {
  const ci = ciOf(m);
  if (!isNum(m.value)) return { label: "Not measured", tone: "neutral", distinguishable: false };
  if (!ci) return { label: "No interval recorded", tone: "neutral", distinguishable: false };
  if (ci[0] <= 0 && ci[1] >= 0) return { label: "Not distinguishable", tone: "neutral", distinguishable: false };
  const up = m.value > 0;
  const good = direction === "higher" ? up : !up;
  if (resource) return { label: up ? "Costs more" : "Costs less", tone: good ? "success" : "warn", distinguishable: true };
  return { label: good ? "Better" : "Worse", tone: good ? "success" : "warn", distinguishable: true };
}

/** Tone for a signed number on its own: negative values are flagged, never silently neutral. */
export function signTone(value: number | null | undefined, direction: Direction = "higher"): StatusTone {
  if (!isNum(value) || value === 0) return "neutral";
  const good = direction === "higher" ? value > 0 : value < 0;
  return good ? "success" : "warn";
}

/** Before/after reading for a rate whose better direction is known. */
export function changeVerdict(before: number | null, after: number | null, direction: Direction): DeltaVerdict {
  if (!isNum(before) || !isNum(after)) return { label: "Not measured", tone: "neutral", distinguishable: false };
  if (before === after) return { label: "No change", tone: "neutral", distinguishable: false };
  const good = direction === "higher" ? after > before : after < before;
  return { label: good ? "Improved" : "Worse", tone: good ? "success" : "warn", distinguishable: true };
}

/** Better direction for the verifier rates (by metric id suffix). */
export function verifierDirection(id: string): Direction {
  return /retention$/.test(id) ? "higher" : "lower";
}

/** Standard-vs-research rows that measure spend (calls, tokens, cost, time) rather than quality. */
const RESOURCE_ROWS = /^(model_calls|tool_calls|retrieval_calls|tokens_total|cost_usd|latency_)/;
export function isResourceRow(rowId: string): boolean {
  return RESOURCE_ROWS.test(rowId);
}

export const DECISION_OUTCOME: Record<
  EvalCatalog["retrieval"]["decisions"][number]["outcome"],
  { label: string; tone: StatusTone }
> = {
  adopted: { label: "Adopted", tone: "success" },
  rejected: { label: "Rejected", tone: "danger" },
  not_adopted: { label: "Not adopted", tone: "warn" },
};

// ── Provenance ────────────────────────────────────────────────────────────────────────────

/** Every provenance block in the catalog with a display label. */
export function allProvenance(c: EvalCatalog): { id: string; label: string; provenance: EvalProvenance }[] {
  return [
    ...c.retrieval.runs.map((r) => ({ id: r.run_id, label: `Retrieval: ${r.label}`, provenance: r.provenance })),
    { id: "p3-grounded-live", label: "Grounded answers", provenance: c.grounded.provenance },
    ...c.research_tradeoff.map((r) => ({
      id: `research-${r.split}`,
      label: `Standard vs research (${r.split})`,
      provenance: r.provenance,
    })),
    ...c.analytics.map((a) => ({ id: `analytics-${a.split}`, label: `Analytics (${a.split})`, provenance: a.provenance })),
  ];
}

const dirname = (p: string) => p.slice(0, p.lastIndexOf("/"));

/** Git commit for an artifact: the run whose results file (or folder) it belongs to, if any. */
export function gitForPath(c: EvalCatalog, path: string): string | null {
  const runs = allProvenance(c).map((p) => p.provenance);
  const exact = runs.find((p) => p.path === path && p.git);
  if (exact) return exact.git;
  const sibling = runs.find((p) => p.git && dirname(p.path) === dirname(path));
  return sibling?.git ?? null;
}

export function sha256ForPath(c: EvalCatalog, path: string): string | null {
  return c.sources.find((s) => s.path === path)?.sha256 ?? null;
}

export function shortHash(hash: string | null | undefined, keep = 10): string {
  return hash ? hash.slice(0, keep) : EMPTY;
}

/** Pointer or anchor of a source, in the form shown next to the path. */
export function sourceLocator(source: EvalSource): string {
  return source.kind === "json" ? source.pointer : `#${source.anchor}`;
}

// ── Lookups ───────────────────────────────────────────────────────────────────────────────

export function metricById(metrics: EvalMetric[], id: string): EvalMetric | undefined {
  return metrics.find((m) => m.id === id);
}

export function caveatsFor(c: EvalCatalog, section: string): EvalCatalog["caveats"] {
  return c.caveats.filter((cv) => cv.applies_to.includes(section));
}

/** Analytics metrics joined across splits by the id after `p5.<split>.`. */
export function joinBySuffix(
  groups: { split: string; metrics: EvalMetric[] }[],
): { key: string; label: string; bySplit: Record<string, EvalMetric | undefined> }[] {
  const order: string[] = [];
  const rows = new Map<string, { label: string; bySplit: Record<string, EvalMetric | undefined> }>();
  for (const g of groups) {
    for (const m of g.metrics) {
      const key = m.id.split(".").slice(2).join(".") || m.id;
      if (!rows.has(key)) {
        order.push(key);
        rows.set(key, { label: m.label, bySplit: {} });
      }
      rows.get(key)!.bySplit[g.split] = m;
    }
  }
  return order.map((key) => ({ key, ...rows.get(key)! }));
}

/** The category whose metric `metricSuffix` is lowest, so weak spots are named plainly. */
export function weakestCategory(
  byCategory: EvalCatalog["grounded"]["by_category"],
  metricSuffix: string,
): { category: string; metric: EvalMetric } | null {
  let worst: { category: string; metric: EvalMetric } | null = null;
  for (const c of byCategory) {
    const m = c.metrics.find((x) => x.id.endsWith(`.${metricSuffix}`));
    if (!m || !isNum(m.value)) continue;
    if (!worst || m.value < (worst.metric.value as number)) worst = { category: c.category, metric: m };
  }
  return worst;
}

/** Grouping of the grounded-answer metrics by id; unknown ids land in "other" so none are dropped. */
export const GROUNDED_GROUPS: { id: string; title: string; ids: string[] }[] = [
  { id: "abstention", title: "Abstention", ids: ["p3.insufficient_correct", "p3.over_refusal"] },
  {
    id: "numeric",
    title: "Numeric faithfulness",
    ids: ["p3.cited_units", "p3.cited_units_flagged", "p3.uncited_numbers_absent", "p3.numeric_units_dropped"],
  },
  {
    id: "repair",
    title: "Regeneration and fallback",
    ids: ["p3.regenerated", "p3.fallback_after_verification", "p3.repairs_total"],
  },
  { id: "latency", title: "Latency", ids: ["p3.first_token_p50", "p3.first_token_p95", "p3.total_p50", "p3.total_p95"] },
  {
    id: "usage",
    title: "Tokens and cost (as recorded by the eval harness)",
    ids: [
      "p3.input_tokens_total",
      "p3.output_tokens_total",
      "p3.cache_read_tokens_total",
      "p3.input_tokens_mean",
      "p3.output_tokens_mean",
      "p3.cost_total",
      "p3.cost_per_model_run",
    ],
  },
];

const SHOWN_ELSEWHERE = new Set(["p3.citation_resolvability", "p3.cross_workspace_leaks"]);

export function groupGroundedMetrics(metrics: EvalMetric[]): { id: string; title: string; metrics: EvalMetric[] }[] {
  const used = new Set<string>(SHOWN_ELSEWHERE);
  const groups = GROUNDED_GROUPS.map((g) => {
    const ms = g.ids.map((id) => metricById(metrics, id)).filter((m): m is EvalMetric => !!m);
    ms.forEach((m) => used.add(m.id));
    return { id: g.id, title: g.title, metrics: ms };
  });
  const other = metrics.filter((m) => !used.has(m.id));
  if (other.length) groups.push({ id: "other", title: "Other measures", metrics: other });
  return groups.filter((g) => g.metrics.length > 0);
}

// ── Failure analysis ──────────────────────────────────────────────────────────────────────

export const EVAL_RUN_IDS: readonly EvalRunId[] = [
  "p2-dev-final",
  "p2-test-c3",
  "p3-grounded-live",
  "p4-research-dev",
  "p4-research-test",
  "p5-analytics-dev",
  "p5-analytics-holdout",
];

export function isEvalRunId(value: string | null | undefined): value is EvalRunId {
  return !!value && (EVAL_RUN_IDS as readonly string[]).includes(value);
}

export function bucketLabel(c: EvalCatalog, runId: EvalRunId, bucket: string | null): string {
  if (!bucket) return "All items";
  const run = c.failure_runs.find((r) => r.run_id === runId);
  return run?.buckets.find((b) => b.id === bucket)?.label ?? bucket.replace(/_/g, " ");
}

/** Evidence handle "WS/SOURCE-CODE@v1:LOCATOR" split for a compact chip ("SOURCE-CODE · LOCATOR"). */
export function parseHandle(handle: string): { source: string; locator: string } {
  const m = /^(?:[^/]+\/)?([^@:]+)(?:@[^:]*)?(?::(.+))?$/.exec(handle);
  return m ? { source: m[1], locator: m[2] ?? "" } : { source: handle, locator: "" };
}

export type AnswerPart = { kind: "text"; text: string } | { kind: "cite"; handle: string } | { kind: "inference" };
export type AnswerBlock = { kind: "heading" | "bullet" | "para"; parts: AnswerPart[] };

const MARKER = /\[\[([^[\]\n]{1,160})\]\]|\[\s*inference\s*\]/gi;

export function splitInline(text: string): AnswerPart[] {
  const parts: AnswerPart[] = [];
  let last = 0;
  for (const m of text.matchAll(MARKER)) {
    if (m.index > last) parts.push({ kind: "text", text: text.slice(last, m.index) });
    parts.push(m[1] ? { kind: "cite", handle: m[1].trim() } : { kind: "inference" });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ kind: "text", text: text.slice(last) });
  return parts;
}

const stripEmphasis = (s: string) => s.replace(/\*\*(.+?)\*\*/g, "$1").replace(/`([^`]+)`/g, "$1");

/**
 * Stored answer Markdown as plain blocks (headings, bullets, paragraphs) with citation markers
 * split out. Rendered as React text only, so stored content can never inject markup.
 */
export function parseAnswer(markdown: string): AnswerBlock[] {
  const blocks: AnswerBlock[] = [];
  let para: string[] = [];
  const flush = () => {
    if (para.length) blocks.push({ kind: "para", parts: splitInline(stripEmphasis(para.join(" "))) });
    para = [];
  };
  for (const raw of markdown.split("\n")) {
    const line = raw.trim();
    if (!line) {
      flush();
      continue;
    }
    const heading = /^#{1,6}\s+(.*)$/.exec(line);
    const bullet = /^(?:[-*]|\d+\.)\s+(.*)$/.exec(line);
    if (heading) {
      flush();
      blocks.push({ kind: "heading", parts: [{ kind: "text", text: stripEmphasis(heading[1]) }] });
    } else if (bullet) {
      flush();
      blocks.push({ kind: "bullet", parts: splitInline(stripEmphasis(bullet[1])) });
    } else {
      para.push(line);
    }
  }
  flush();
  return blocks;
}

// ── Load state ────────────────────────────────────────────────────────────────────────────

export type CatalogFailure = "unavailable" | "error";

/** 404 (route absent in production) and 503 EVAL_CATALOG_UNAVAILABLE both mean "not served here". */
export function catalogFailure(error: unknown): CatalogFailure {
  if (error instanceof ApiError && (error.status === 404 || error.code === "EVAL_CATALOG_UNAVAILABLE")) {
    return "unavailable";
  }
  return "error";
}

export const EVAL_TABS = [
  { id: "overview", label: "Overview" },
  { id: "retrieval", label: "Retrieval" },
  { id: "grounded", label: "Grounded answers" },
  { id: "research", label: "Standard vs Research" },
  { id: "analytics", label: "Analytics" },
  { id: "failures", label: "Failure analysis" },
  { id: "provenance", label: "Provenance" },
] as const;

export type EvalTabId = (typeof EVAL_TABS)[number]["id"];

export function evalHref(ws: string, tab?: EvalTabId): string {
  const base = `/w/${encodeURIComponent(ws)}/dev/evaluation`;
  return tab ? `${base}?tab=${tab}` : base;
}

export function evalRunHref(ws: string, runId: EvalRunId, opts: { bucket?: string | null; item?: string | null } = {}): string {
  const q = new URLSearchParams();
  if (opts.bucket) q.set("bucket", opts.bucket);
  if (opts.item) q.set("item", opts.item);
  const qs = q.toString();
  return `${evalHref(ws)}/runs/${encodeURIComponent(runId)}${qs ? `?${qs}` : ""}`;
}

/** Provenance block for the run that produced a failure-analysis item set. */
export function provenanceForRun(c: EvalCatalog, runId: EvalRunId): EvalProvenance | null {
  if (runId.startsWith("p2-")) return c.retrieval.runs.find((r) => r.run_id === runId)?.provenance ?? null;
  if (runId === "p3-grounded-live") return c.grounded.provenance;
  if (runId.startsWith("p4-")) {
    const split = runId.endsWith("-test") ? "test" : "dev";
    return c.research_tradeoff.find((r) => r.split === split)?.provenance ?? null;
  }
  const split = runId.endsWith("-holdout") ? "holdout" : "dev";
  return c.analytics.find((a) => a.split === split)?.provenance ?? null;
}

/** Display value for one stored per-item check (booleans as Yes/No, ratios with three decimals). */
export function formatCheck(key: string, value: number | boolean | null | undefined): string {
  if (value === null || value === undefined) return EMPTY;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (/_ms$/.test(key)) return formatMs(value);
  if (/cost/.test(key)) return formatUsd(value, { digits: 4 });
  if (/coverage|correct|recall|completeness|rate|accuracy|pass/.test(key)) return value.toFixed(3);
  if (Number.isInteger(value)) return formatNumber(value);
  return value.toFixed(3);
}

/** Signed per-item difference ("+4", "−87 ms"); zero has no sign. */
export function formatCheckDelta(key: string, value: number | null | undefined): string {
  if (!isNum(value)) return EMPTY;
  const body = formatCheck(key, Math.abs(value));
  return value > 0 ? `+${body}` : value < 0 ? `${MINUS}${body}` : body;
}

/** Display labels for retrieval arms, from the catalog's run definitions. */
export function armLabels(c: EvalCatalog): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of c.retrieval.runs) for (const a of r.arms) out[a.arm] ??= a.label;
  return out;
}

/** Paging window for item lists: "21–40 of 76". */
export function pageWindow(offset: number, count: number, total: number): string {
  if (total === 0 || count === 0) return `0 of ${formatNumber(total)}`;
  return `${formatNumber(offset + 1)}–${formatNumber(offset + count)} of ${formatNumber(total)}`;
}
