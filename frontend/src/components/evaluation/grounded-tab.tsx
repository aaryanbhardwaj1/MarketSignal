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
  metricById,
  verifierDirection,
  weakestCategory,
} from "@/lib/eval-view";
import { formatNumber, humanize } from "@/lib/format";
import { Caveats, ProvenanceTable } from "./caveats";
import { MetricCell, MetricGrid, MetricSource } from "./metric-bits";
import { MetricGlossary } from "./metric-glossary";

type Gate = EvalCatalog["grounded"]["hard_gates"][number];
type Category = EvalCatalog["grounded"]["by_category"][number];

const sentence = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const catMetric = (c: Category, suffix: string) => c.metrics.find((m) => m.id.endsWith(`.${suffix}`));

function GatesTable({ gates, leaks }: { gates: Gate[]; leaks: EvalMetric | undefined }) {
  const columns: Column<Gate>[] = [
    { key: "label", header: "Safety gate", cell: (g) => <span className="font-medium">{g.label}</span> },
    {
      key: "kn",
      header: "Passed",
      align: "right",
      cell: (g) => (
        <span className="whitespace-nowrap tabular-nums">
          {formatNumber(g.k)} / {formatNumber(g.n)}
        </span>
      ),
    },
    {
      key: "status",
      header: "Result",
      cell: (g) => <Badge tone={g.pass ? "success" : "danger"}>{g.pass ? "Pass" : "Fail"}</Badge>,
    },
    { key: "src", header: <span className="sr-only">Source</span>, cell: (g) => <MetricSource source={g.source} /> },
  ];
  return (
    <div className="flex flex-col gap-3">
      <Table columns={columns} rows={gates} rowKey={(g) => g.id} caption="Hard gates: every item must pass" />
      {leaks && (
        <p className="flex flex-wrap items-center gap-2 text-sm text-secondary">
          Workspace isolation: <span className="font-medium tabular-nums text-primary">{formatEvalValue(leaks.value, leaks.unit)}</span>{" "}
          {leaks.label.toLowerCase()} across all runs. <MetricSource source={leaks.source} />
        </p>
      )}
    </div>
  );
}

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
  const groups = groupGroundedMetrics(g.metrics);
  return (
    <div>
      <p className="max-w-reading text-base text-secondary">
        Live answers generated against a fixed question set. Every citation is checked against stored passages, numbers
        are re-checked against the evidence, and questions without enough evidence must be declined.
      </p>
      <div className="mt-4">
        <MetricGlossary keys={["ci", "pp"]} />
      </div>

      <Section title="Safety gates" description="Hard requirements checked on every item. One failure fails the gate.">
        <GatesTable gates={g.hard_gates} leaks={metricById(g.metrics, "p3.cross_workspace_leaks")} />
      </Section>

      <Section title="Coverage by question category" description="Behaviour pass rate with 95% CI; coverage and numeric correctness are item means.">
        <CategoryTable categories={g.by_category} />
      </Section>

      {groups.map((group) => (
        <Section key={group.id} title={group.title}>
          <MetricGrid metrics={group.metrics} label={group.title} />
        </Section>
      ))}

      <Section
        title="Verifier v1: before and after"
        description="Precision of the answer verifier measured on labelled answer units, on dev and on a separate holdout."
      >
        <div className="grid gap-4 xl:grid-cols-2">
          {g.verifier.map((v) => (
            <VerifierTable key={v.split} split={v} />
          ))}
        </div>
      </Section>

      <Section title="Run provenance">
        <ProvenanceTable rows={[{ id: "grounded", label: "Grounded answers", provenance: g.provenance }]} caption="Grounded answers run provenance" />
      </Section>

      <div className="mt-8">
        <Caveats caveats={caveatsFor(catalog, "grounded")} title="Caveats for grounded answers" />
      </div>
    </div>
  );
}
