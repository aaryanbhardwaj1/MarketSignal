import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { Section } from "@/components/ui/section";
import { Table, type Column } from "@/components/ui/table";
import type { EvalCatalog, EvalMetric } from "@/lib/api/contracts";
import {
  caveatsFor,
  changeVerdict,
  formatEvalValue,
  groupGroundedMetrics,
  verifierDirection,
  weakestCategory,
} from "@/lib/eval-view";
import { formatNumber, humanize } from "@/lib/format";
import { Caveats, ProvenanceTable } from "./caveats";
import { MetricCell, MetricGrid, MetricSource } from "./metric-bits";
import { SAFETY_METRIC_IDS, SafetyGates } from "./dashboard/gate-tiles";
import { MethodTag } from "./dashboard/story-cards";

type Category = EvalCatalog["grounded"]["by_category"][number];

const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const catMetric = (c: Category, suffix: string) => c.metrics.find((m) => m.id.endsWith(`.${suffix}`));

function CategoryTable({ categories }: { categories: Category[] }) {
  const weakest = weakestCategory(categories, "gold_coverage_mean");
  const columns: Column<Category>[] = [
    {
      key: "cat",
      header: "Question category",
      cell: (c) => (
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{sentence(humanize(c.category))}</span>
          {weakest?.category === c.category && <Badge tone="warn">Lowest coverage</Badge>}
        </span>
      ),
    },
    { key: "behaviour", header: "Expected behaviour", align: "right", cell: (c) => <MetricCell metric={catMetric(c, "behaviour")} /> },
    { key: "coverage", header: "Gold evidence coverage", align: "right", cell: (c) => <MetricCell metric={catMetric(c, "gold_coverage_mean")} /> },
    { key: "numeric", header: "Numeric correctness", align: "right", cell: (c) => <MetricCell metric={catMetric(c, "numeric_correct_mean")} /> },
  ];
  return (
    <div className="flex flex-col gap-3">
      {weakest && (
        <Callout tone="warn" title={`Weakest category: ${humanize(weakest.category)} questions.`}>
          Gold evidence coverage was {formatEvalValue(weakest.metric.value, weakest.metric.unit)}
          {weakest.metric.n != null ? ` across ${formatNumber(weakest.metric.n)} items` : ""}. Answers to these questions
          cite less of the expected evidence than other categories. <MetricSource source={weakest.metric.source} />
        </Callout>
      )}
      <Table
        columns={columns}
        rows={categories}
        rowKey={(c) => c.category}
        caption="Answer quality by question category; categories without gold evidence report behaviour only"
      />
    </div>
  );
}

interface VerifierRow {
  id: string;
  label: string;
  before: EvalMetric;
  after: EvalMetric | undefined;
}

function VerifierTable({ split }: { split: EvalCatalog["grounded"]["verifier"][number] }) {
  const rows: VerifierRow[] = split.before.map((b) => ({
    id: b.id,
    label: b.label,
    before: b,
    after: split.after.find((a) => a.id.split(".").pop() === b.id.split(".").pop()),
  }));
  const columns: Column<VerifierRow>[] = [
    {
      key: "label",
      header: "Measure",
      cell: (r) => (
        <span className="flex flex-col">
          <span className="font-medium">{r.label}</span>
          <span className="text-xs text-muted">{verifierDirection(r.id) === "higher" ? "Higher is better" : "Lower is better"}</span>
        </span>
      ),
    },
    { key: "before", header: "Before", align: "right", cell: (r) => <MetricCell metric={r.before} /> },
    { key: "after", header: "After verifier v1", align: "right", cell: (r) => <MetricCell metric={r.after} /> },
    {
      key: "read",
      header: "Change",
      cell: (r) => {
        const v = changeVerdict(r.before.value, r.after?.value ?? null, verifierDirection(r.id));
        return <Badge tone={v.tone}>{v.label}</Badge>;
      },
    },
  ];
  return (
    <Table
      columns={columns}
      rows={rows}
      rowKey={(r) => r.id}
      showCaption
      caption={split.split === "holdout" ? "Holdout split" : "Dev split"}
      density="compact"
    />
  );
}

export function GroundedTab({ catalog }: { catalog: EvalCatalog }) {
  const g = catalog.grounded;
  const groups = groupGroundedMetrics(g.metrics, SAFETY_METRIC_IDS(g.metrics));
  return (
    <div>
      <p className="max-w-reading text-base text-secondary">
        Live answers generated against a frozen question set. Every citation is checked against stored passages, numbers
        are re-checked against the evidence, and questions without enough evidence must be declined.
      </p>
      <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted">
        <MethodTag /> Every figure on this tab is computed by a deterministic check over the stored run outputs; no model
        judged it.
      </p>

      <Section title="Safety gates" description="Citation integrity, workspace isolation and abstention, with counts as recorded.">
        <SafetyGates gates={g.hard_gates} metrics={g.metrics} />
      </Section>

      <Section
        title="Verifier v1: before and after"
        description="Precision of the answer verifier on labelled answer units, on dev and on a separate holdout. n is the number of labelled units per rate."
      >
        <div className="grid gap-4 xl:grid-cols-2">
          {g.verifier.map((v) => (
            <VerifierTable key={v.split} split={v} />
          ))}
        </div>
      </Section>

      <Section title="By question category" description="Behaviour pass rate with 95% CI; coverage and numeric correctness are item means.">
        <CategoryTable categories={g.by_category} />
      </Section>

      {groups.map((group) => (
        <Section key={group.id} title={group.title}>
          <MetricGrid metrics={group.metrics} label={group.title} />
        </Section>
      ))}

      <Section title="Run provenance">
        <ProvenanceTable rows={[{ id: "grounded", label: "Grounded answers", provenance: g.provenance }]} caption="Grounded answers run provenance" />
      </Section>

      <div className="mt-8">
        <Caveats caveats={caveatsFor(catalog, "grounded")} title="Caveats for grounding and safety" />
      </div>
    </div>
  );
}
