import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { DevDetails } from "@/components/ui/disclosure";
import { KeyValueList } from "@/components/ui/key-value";
import { Table, type Column } from "@/components/ui/table";
import type { EvalItem, EvalProvenance } from "@/lib/api/contracts";
import { checkLabel, formatCheck, formatCheckDelta } from "@/lib/eval-view";
import { stopReason, terminationState, type Humanized } from "@/lib/labels";
import { toolStatusLabel } from "@/lib/telemetry-view";
import { formatDateTime, formatNumber, humanize } from "@/lib/format";
import { AnswerText, HandleChip, InlineText } from "./answer-text";

const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

type Of<P extends EvalItem["phase"]> = Extract<EvalItem, { phase: P }>;

function Block({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="border-t border-border pt-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-semibold text-primary">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** Label with its stored code beside it, as Telemetry shows codes on developer pages. */
function Coded({ h }: { h: Humanized }) {
  if (!h.code) return <span>Not recorded</span>;
  return (
    <span>
      {h.known ? h.label : h.code}
      {h.known && <span className="ml-1 font-mono">({h.code})</span>}
    </span>
  );
}

function CodedBadge({ h }: { h: Humanized }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Badge tone={h.tone ?? "neutral"}>{h.known ? h.label : h.code || "Not recorded"}</Badge>
      {h.known && <span className="font-mono text-xs text-muted">{h.code}</span>}
    </span>
  );
}

function HandleList({ handles, highlight, empty }: { handles: string[]; highlight?: Set<string>; empty: string }) {
  if (handles.length === 0) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <ul className="flex flex-wrap gap-1.5">
      {handles.map((h, i) => (
        <li key={`${h}-${i}`} className="flex items-center gap-1">
          <HandleChip handle={h} marked={highlight?.has(h)} />
          {highlight?.has(h) && <span className="sr-only">(expected evidence)</span>}
        </li>
      ))}
    </ul>
  );
}

function Checks({ checks }: { checks: Record<string, number | boolean | null> }) {
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3 lg:grid-cols-4">
      {Object.entries(checks).map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="truncate text-sm text-muted" title={k}>
            {checkLabel(k)}
          </dt>
          <dd className="text-base tabular-nums text-primary">{formatCheck(k, v)}</dd>
        </div>
      ))}
    </dl>
  );
}

const yesNo = (ok: boolean | null, yes: string, no: string, unknown = "Not recorded") =>
  ok === null ? <Badge tone="neutral">{unknown}</Badge> : <Badge tone={ok ? "success" : "danger"}>{ok ? yes : no}</Badge>;

function RetrievalDetail({ item, labels }: { item: Of<"retrieval">; labels: Record<string, string> }) {
  const expected = new Set(item.expected_handles);
  const arms = Object.entries(item.by_arm).map(([arm, v]) => ({ arm, ...v }));
  const columns: Column<(typeof arms)[number]>[] = [
    { key: "arm", header: "Method", width: "18%", cell: (a) => <span className="font-medium">{labels[a.arm] ?? humanize(a.arm)}</span> },
    { key: "hit", header: "In top 10", width: "11%", cell: (a) => yesNo(a.hit_at_10, "Found", "Missed") },
    {
      key: "ranks",
      header: "Expected fact rank",
      width: "13%",
      cell: (a) => (
        <span className="tabular-nums">{a.fact_ranks.map((r) => (r == null ? "not retrieved" : `#${r}`)).join(", ") || "-"}</span>
      ),
    },
    { key: "top", header: "Top 10 retrieved passages", cell: (a) => <HandleList handles={a.top.slice(0, 10)} highlight={expected} empty="None" /> },
  ];
  return (
    <>
      <Block title="Expected evidence">
        <HandleList handles={item.expected_handles} highlight={expected} empty="No expected evidence recorded." />
      </Block>
      <Block title="Retrieved by method" aside={<span className="text-xs text-muted">Highlighted passages are expected evidence</span>}>
        <Table columns={columns} rows={arms} rowKey={(a) => a.arm} caption="Retrieval results per method for this item" density="compact" />
      </Block>
    </>
  );
}

function GroundedDetail({ item }: { item: Of<"grounded"> }) {
  const gold = new Set(item.gold_handles);
  return (
    <>
      {item.failure && (
        <Callout tone="warn" title={`Labelled failure: ${humanize(item.failure.final_classification)}`}>
          <p>
            <span className="font-medium text-primary">Root cause. </span>
            <InlineText text={item.failure.root_cause} />
          </p>
          <p className="mt-1.5">
            <span className="font-medium text-primary">User impact. </span>
            <InlineText text={item.failure.user_impact} />
          </p>
        </Callout>
      )}
      <Block title="Final answer (as stored)" aside={<CodedBadge h={terminationState(item.termination_state)} />}>
        <AnswerText markdown={item.answer_markdown} />
      </Block>
      <Block title="Expected evidence">
        <HandleList handles={item.gold_handles} highlight={gold} empty="This question has no expected evidence (it should be declined or is behaviour-only)." />
      </Block>
      <Block title="Cited evidence">
        <HandleList handles={item.cited_handles} highlight={gold} empty="No citations in the stored answer." />
      </Block>
      <Block title="Checks">
        <Checks checks={item.checks} />
      </Block>
    </>
  );
}

function ResearchDetail({ item }: { item: Of<"research"> }) {
  const keys = Object.keys(item.delta);
  const rows = keys.map((k) => ({ k, s: item.standard.metrics[k] ?? null, r: item.research.metrics[k] ?? null, d: item.delta[k] }));
  const columns: Column<(typeof rows)[number]>[] = [
    { key: "k", header: "Measure", cell: (r) => sentence(humanize(r.k)) },
    { key: "s", header: "Standard", align: "right", cell: (r) => <span className="tabular-nums">{formatCheck(r.k, r.s)}</span> },
    { key: "r", header: "Research", align: "right", cell: (r) => <span className="tabular-nums">{formatCheck(r.k, r.r)}</span> },
    { key: "d", header: "Difference", align: "right", cell: (r) => <span className="tabular-nums">{formatCheckDelta(r.k, r.d)}</span> },
  ];
  return (
    <>
      <Block title="Per-item measures">
        <Table columns={columns} rows={rows} rowKey={(r) => r.k} caption="Standard and research measures for this item" density="compact" />
      </Block>
      <div className="grid gap-4 border-t border-border pt-4 xl:grid-cols-2">
        <div className="min-w-0">
          <h3 className="mb-2 text-base font-semibold text-primary">Standard answer</h3>
          <AnswerText markdown={item.standard.answer_markdown} />
        </div>
        <div className="min-w-0">
          <h3 className="mb-2 text-base font-semibold text-primary">Research answer</h3>
          <AnswerText markdown={item.research.answer_markdown} />
        </div>
      </div>
      <Block
        title="Research steps"
        aside={
          <span className="text-xs text-muted">
            {formatNumber(item.research.tool_calls)} tool calls · stopped: <Coded h={stopReason(item.research.stop_reason)} />
          </span>
        }
      >
        <ol className="flex flex-col gap-1 text-sm">
          {item.research.trace.map((t, i) => (
            <li key={i} className="flex items-center gap-3">
              <span className="w-12 tabular-nums text-muted">Step {t.step}</span>
              <span className="font-mono">{t.tool}</span>
              <Badge tone={t.status === "ok" ? "success" : "warn"} title={t.status}>
                {toolStatusLabel(t.status)}
              </Badge>
            </li>
          ))}
        </ol>
      </Block>
    </>
  );
}

function AnalyticsDetail({ item }: { item: Of<"analytics"> }) {
  return (
    <>
      <Block title="Routing and result">
        <KeyValueList
          columns={2}
          items={[
            { label: "Expected task type", value: humanize(item.task_type) },
            { label: "Routed as", value: item.routed_task_type ? humanize(item.routed_task_type) : "Not recorded" },
            { label: "Routing", value: yesNo(item.task_type_correct, "Correct", "Wrong") },
            { label: "Gold values", value: yesNo(item.values_matched, "All matched", "Not all matched", "Not applicable") },
            { label: "Exact-result accuracy", value: <span className="tabular-nums">{formatCheck("accuracy", item.exact_result_accuracy)}</span> },
          ]}
        />
      </Block>
      <Block title="Final answer (as stored)">
        <AnswerText markdown={item.answer_markdown} />
      </Block>
      <Block title="Expected and computed values">
        <div className="flex flex-col gap-2">
          <DevDetails summary="Gold values" data={item.gold_values} />
          <DevDetails summary="Computed results" data={item.computed} />
        </div>
      </Block>
    </>
  );
}

function Configuration({ provenance }: { provenance: EvalProvenance | null }) {
  if (!provenance) return null;
  return (
    <Block title="Configuration">
      <KeyValueList
        columns={2}
        items={[
          {
            label: "Dataset",
            value:
              provenance.dataset.version && provenance.dataset.version !== provenance.dataset.name
                ? `${provenance.dataset.name} (${provenance.dataset.version})`
                : provenance.dataset.name,
          },
          { label: "Split", value: provenance.split ?? "Not recorded" },
          { label: "Model", value: <span className="font-mono text-sm">{provenance.model ?? "Not applicable"}</span> },
          { label: "Config hash", value: <span className="font-mono text-sm">{provenance.config_hash ?? "Not recorded"}</span> },
          { label: "Commit", value: <span className="font-mono text-sm">{provenance.git ?? "Not recorded"}</span> },
          { label: "Recorded", value: formatDateTime(provenance.at) },
        ]}
      />
    </Block>
  );
}

export function itemCategory(item: EvalItem): string | null {
  if (item.phase === "retrieval" || item.phase === "grounded") return item.category;
  if (item.phase === "analytics") return item.task_type;
  return null;
}

/** One evaluation item as recorded: no reasoning text exists or is shown. */
export function ItemDetail({
  item,
  provenance,
  armLabels = {},
}: {
  item: EvalItem;
  provenance: EvalProvenance | null;
  armLabels?: Record<string, string>;
}) {
  const category = itemCategory(item);
  return (
    <article aria-labelledby="eval-item-question" className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-5">
      <header>
        <p className="flex flex-wrap items-center gap-2 text-sm text-muted">
          <span className="font-mono">{item.item_id}</span>
          {category && <Badge tone="neutral">{humanize(category)}</Badge>}
          {item.phase === "retrieval" && item.bucket && <Badge tone="warn">{humanize(item.bucket)}</Badge>}
        </p>
        <h2 id="eval-item-question" className="mt-1.5 text-md font-semibold text-primary">
          {item.question}
        </h2>
      </header>
      {item.phase === "retrieval" && <RetrievalDetail item={item} labels={armLabels} />}
      {item.phase === "grounded" && <GroundedDetail item={item} />}
      {item.phase === "research" && <ResearchDetail item={item} />}
      {item.phase === "analytics" && <AnalyticsDetail item={item} />}
      <Configuration provenance={provenance} />
      <p className="border-t border-border pt-3 text-xs text-muted">
        Stored output and checks only. Model reasoning is not recorded by the evaluation harness and is not shown.
      </p>
    </article>
  );
}
