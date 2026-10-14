import { Check, Minus, TriangleAlert, X } from "lucide-react";
import type { StatusTone } from "@/components/ui/tone";
import type { EvalCatalog, EvalMetric } from "@/lib/api/contracts";
import { cx } from "@/lib/cx";
import { formatCountOf, isKOfN, primaryDisplay } from "@/lib/eval-view";
import { MetricSource } from "../metric-bits";
import { gateMetric, safetyMeasures } from "./derive";
import { MethodTag } from "./story-cards";

type Gate = EvalCatalog["grounded"]["hard_gates"][number];

const TILE: Record<StatusTone, string> = {
  success: "border-success/25",
  warn: "border-warn/40 bg-warn-subtle",
  danger: "border-danger/50 bg-danger-subtle",
  info: "border-info/25",
  neutral: "border-border",
};
const ICON_TONE: Record<StatusTone, string> = {
  success: "text-success",
  warn: "text-warn",
  danger: "text-danger",
  info: "text-info",
  neutral: "text-muted",
};
const ICON = { success: Check, danger: X, warn: TriangleAlert, info: Minus, neutral: Minus } as const;

function Tile({ metric, tone, state, testState }: { metric: EvalMetric; tone: StatusTone; state: string; testState: string }) {
  const Icon = ICON[tone];
  const count = isKOfN(metric) ? null : formatCountOf(metric);
  return (
    <li data-state={testState} className={cx("flex min-w-0 flex-col rounded-lg border bg-surface px-4 py-3", TILE[tone])}>
      <div className="flex items-center gap-2">
        <Icon aria-hidden className={cx("size-4 shrink-0", ICON_TONE[tone])} strokeWidth={2.25} />
        <span className={cx("text-sm font-semibold", ICON_TONE[tone])}>{state}</span>
      </div>
      <p className="mt-1.5 text-sm text-secondary">{metric.label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-primary">
        {metric.value == null ? "Not measured" : primaryDisplay(metric)}
      </p>
      <span className="mt-1 flex flex-wrap items-center gap-2 text-xs tabular-nums text-muted">
        {count && <span>{count}</span>}
        <MethodTag />
        <MetricSource source={metric.source} />
      </span>
    </li>
  );
}

/** Hard gates (pass/fail exactly as recorded) followed by the safety measures, each with n / N and source. */
export function SafetyGates({ gates, metrics }: { gates: Gate[]; metrics: EvalMetric[] }) {
  const measures = safetyMeasures(metrics);
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h3 className="mb-2 text-base font-semibold text-primary">Hard gates: every item must pass</h3>
        <ul aria-label="Hard gates" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {gates.map((g) => (
            <Tile
              key={g.id}
              metric={gateMetric(g)}
              tone={g.pass ? "success" : "danger"}
              state={g.pass ? "Pass" : "Fail"}
              testState={g.pass ? "pass" : "fail"}
            />
          ))}
        </ul>
      </div>
      {measures.length > 0 && (
        <div>
          <h3 className="mb-2 text-base font-semibold text-primary">Safety measures</h3>
          <ul aria-label="Safety measures" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {measures.map((m) => (
              <Tile key={m.metric.id} metric={m.metric} tone={m.tone} state={m.state} testState={m.tone} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export const SAFETY_METRIC_IDS = (metrics: EvalMetric[]): string[] => safetyMeasures(metrics).map((m) => m.metric.id);
