import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Section } from "@/components/ui/section";
import { Table, type Column } from "@/components/ui/table";
import type { EvalCatalog } from "@/lib/api/contracts";
import { caveatsFor, joinBySuffix } from "@/lib/eval-view";
import { Caveats, ProvenanceTable } from "./caveats";
import { MetricCell } from "./metric-bits";

type JoinedRow = ReturnType<typeof joinBySuffix>[number];

const SPLIT_LABEL: Record<string, string> = { dev: "Dev", holdout: "Holdout" };

/** Rows grouped for reading: accuracy first, then faithfulness, then speed and spend. */
const SECTIONS: { title: string; match: RegExp }[] = [
  { title: "Accuracy and routing", match: /accuracy|recognition|matched/ },
  { title: "Faithfulness", match: /faithfulness|unsupported/ },
  { title: "Latency, calls and cost", match: /./ },
];

export function AnalyticsTab({ catalog }: { catalog: EvalCatalog }) {
  const splits = catalog.analytics.map((a) => a.split);
  const rows = joinBySuffix(catalog.analytics);
  const used = new Set<string>();
  const sections = SECTIONS.map((s) => {
    const picked = rows.filter((r) => !used.has(r.key) && s.match.test(r.key));
    picked.forEach((r) => used.add(r.key));
    return { ...s, rows: picked };
  }).filter((s) => s.rows.length > 0);

  const columns: Column<JoinedRow>[] = [
    { key: "label", header: "Measure", width: "50%", cell: (r) => <span className="font-medium">{r.label}</span> },
    ...splits.map(
      (split): Column<JoinedRow> => ({
        key: split,
        header: SPLIT_LABEL[split] ?? split,
        align: "right",
        width: `${50 / Math.max(splits.length, 1)}%`,
        cell: (r) => <MetricCell metric={r.bySplit[split]} />,
      }),
    ),
  ];

  return (
    <div>
      <p className="max-w-reading text-base text-secondary">
        Structured questions are routed to deterministic calculations over the uploaded tables. Dev and holdout results
        are shown side by side; where the holdout is weaker, it is shown as measured.
      </p>
      <div className="mt-6">
        <Caveats caveats={caveatsFor(catalog, "analytics")} title="Caveats for analytics" />
      </div>

      {sections.map((s) => (
        <Section key={s.title} title={s.title}>
          <Table columns={columns} rows={s.rows} rowKey={(r) => r.key} caption={`${s.title}: dev and holdout`} />
        </Section>
      ))}

      <Section title="Run provenance">
        <ProvenanceTable
          rows={catalog.analytics.map((a) => ({ id: a.split, label: `Analytics (${SPLIT_LABEL[a.split] ?? a.split})`, provenance: a.provenance }))}
          caption="Analytics run provenance"
        />
      </Section>

      <Section title="Superseded attempts" description="Earlier runs that were replaced. They are kept for the record and excluded from the figures above.">
        <ul className="flex flex-col gap-2">
          {catalog.superseded.map((s) => (
            <Card key={s.path} as="li" padding="none" className="px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="neutral">Superseded</Badge>
                <span className="text-base font-medium text-primary">{s.label}</span>
              </div>
              <p className="mt-1 text-base text-secondary">{s.reason}</p>
              <p className="mt-1 break-all font-mono text-xs text-muted">{s.path}</p>
            </Card>
          ))}
        </ul>
      </Section>
    </div>
  );
}
