import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { EvalMetric } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import { EVAL_TABS, evalHref, formatCi, formatCountOf, formatEvalValue, formatSigned, isKOfN, primaryDisplay } from "@/lib/eval-view";
import { MetricSource } from "../metric-bits";
import type { StoryCard, StoryFigure } from "./derive";

const ACCENT: Record<StoryCard["tone"], string> = {
  success: "before:bg-success",
  warn: "before:bg-warn",
  danger: "before:bg-danger",
  info: "before:bg-accent",
  neutral: "before:bg-border-strong",
};

function MetricFigure({ metric, signed }: { metric: EvalMetric; signed?: boolean }) {
  const ci = formatCi(metric, { signed });
  const count = isKOfN(metric) ? null : formatCountOf(metric);
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted">{metric.label}</dt>
      <dd className="mt-0.5 flex flex-wrap items-baseline gap-x-2">
        <span className="text-lg font-semibold tabular-nums text-primary">
          {metric.value == null ? "Not measured" : signed ? formatSigned(metric.value, metric.unit) : primaryDisplay(metric)}
        </span>
        <span className="flex flex-wrap items-baseline gap-x-2 text-xs tabular-nums text-muted">
          {ci && <span>{ci}</span>}
          {count && <span>{count}</span>}
          <MetricSource source={metric.source} />
        </span>
      </dd>
    </div>
  );
}

function PairFigure({ figure }: { figure: Extract<StoryFigure, { kind: "pair" }> }) {
  const { standard, research } = figure;
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted">{figure.label}</dt>
      <dd className="mt-0.5 flex flex-wrap items-baseline gap-x-2 text-sm tabular-nums">
        <span className="text-secondary">Standard</span>
        <span className="font-medium text-primary">{formatEvalValue(standard.value, standard.unit)}</span>
        <MetricSource source={standard.source} />
        <span className="text-muted" aria-hidden>
          ·
        </span>
        <span className="text-secondary">Research</span>
        <span className="font-medium text-primary">{formatEvalValue(research.value, research.unit)}</span>
        <MetricSource source={research.source} />
      </dd>
    </div>
  );
}

/** Overview headline: four cards that tell how the configuration was chosen, each figure with its source. */
export function StoryCards({ cards, ws }: { cards: StoryCard[]; ws?: string }) {
  return (
    <ol aria-label="Headline findings" className="grid gap-3 md:grid-cols-2">
      {cards.map((card) => (
        <li
          key={card.id}
          className={cx(
            "relative flex min-w-0 flex-col overflow-hidden rounded-lg border border-border bg-surface p-4 shadow-raised",
            "before:absolute before:inset-y-0 before:left-0 before:w-0.5",
            ACCENT[card.tone],
          )}
        >
          <div className="flex items-start justify-between gap-3">
            <h3 className="text-base font-semibold text-primary">{card.title}</h3>
            <Badge tone={card.tone}>{card.verdict}</Badge>
          </div>
          {card.summary && <p className="mt-1 text-sm text-secondary">{card.summary}</p>}
          <dl className="mt-3 flex flex-col gap-3">
            {card.figures.map((f, i) =>
              f.kind === "metric" ? (
                <MetricFigure key={f.metric.id} metric={f.metric} signed={f.signed} />
              ) : (
                <PairFigure key={`${f.label}-${i}`} figure={f} />
              ),
            )}
          </dl>
          {ws && (
            <Link
              href={evalHref(ws, card.tab)}
              className="mt-auto inline-flex items-center gap-1 self-start pt-3 text-sm text-accent-text hover:underline"
            >
              {EVAL_TABS.find((t) => t.id === card.tab)?.label}
              <ArrowRight aria-hidden className="size-3.5" />
            </Link>
          )}
        </li>
      ))}
    </ol>
  );
}

/** Marks a figure as computed by a deterministic check (vs a model-judged score elsewhere). */
export function MethodTag({ kind = "deterministic" }: { kind?: "deterministic" | "model-judged" }) {
  return (
    <span
      className="inline-flex items-center rounded-md border border-border px-1.5 text-2xs font-medium text-secondary"
      title={
        kind === "deterministic"
          ? "Computed by a deterministic check over stored outputs; no model judged it."
          : "Scored by a model acting as judge."
      }
    >
      {kind === "deterministic" ? "Deterministic metric" : "Model-judged"}
    </span>
  );
}
