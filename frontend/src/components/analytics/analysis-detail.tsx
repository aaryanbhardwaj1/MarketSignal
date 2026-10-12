import type { Analysis } from "@/lib/api/contracts";
import { formatDateTime, formatNumber } from "@/lib/format";
import { BarList } from "../ui/bar-list";
import { Callout } from "../ui/callout";
import { DevDetails } from "../ui/disclosure";
import { KeyValueList } from "../ui/key-value";
import { Section } from "../ui/section";
import { Table, type Column } from "../ui/table";
import {
  analysisState,
  categoryLabel,
  describeFilter,
  formatListingCell,
  humanizeKey,
  isNumericColumn,
  tableLabel,
  rowBase,
  rowLabel,
  unitLabel,
} from "./analysis-format";
import type { AnalysisRow } from "@/lib/api/contracts";
import { Card } from "../ui/card";

interface IndexedRow {
  index: number;
  row: AnalysisRow;
}

function ResultBody({ analysis }: { analysis: Analysis }) {
  const rows: IndexedRow[] = analysis.rows.map((row, index) => ({ index, row }));
  if (analysis.op === "filter_rows" && analysis.columns && analysis.columns.length > 0) {
    const columns: Column<IndexedRow>[] = analysis.columns.map((col) => ({
      key: col,
      header: humanizeKey(col),
      align: isNumericColumn(analysis.rows, col) ? "right" : "left",
      cell: ({ row }) => formatListingCell(col, row.group[col]),
    }));
    return <Table caption={analysis.title} columns={columns} rows={rows} rowKey={(r) => String(r.index)} />;
  }

  const groupKeys = analysis.group_by.length > 0 ? analysis.group_by : Object.keys(analysis.rows[0]?.group ?? {});
  const hasBase = analysis.rows.some((r) => rowBase(r, analysis) != null);
  const columns: Column<IndexedRow>[] = [
    ...groupKeys.map((key) => ({
      key: `g-${key}`,
      header: humanizeKey(key),
      cell: ({ row }: IndexedRow) => rowLabel(row, [key]),
    })),
    {
      key: "value",
      header: unitLabel(analysis.unit),
      align: "right" as const,
      cell: ({ row }: IndexedRow) => <span className="font-medium">{row.display ?? "-"}</span>,
    },
    ...(hasBase
      ? [{ key: "base", header: "Base", align: "right" as const, cell: ({ row }: IndexedRow) => <span className="text-secondary">{rowBase(row, analysis) ?? "-"}</span> }]
      : []),
  ];
  const table = <Table caption={analysis.title} columns={columns} rows={rows} rowKey={(r) => String(r.index)} />;

  if (analysis.presentation !== "bar") return table;
  const items = analysis.rows
    .filter((r) => r.value != null)
    .map((r, i) => ({ label: rowLabel(r, groupKeys), value: r.value as number, display: r.display ?? "-", emphasis: i === 0 }));
  return (
    <div className="flex flex-col gap-4">
      <BarList items={items} ariaLabel={analysis.title} />
      <details className="group">
        <summary className="cursor-pointer list-none rounded-sm text-sm font-medium text-accent-text hover:underline [&::-webkit-details-marker]:hidden">
          Show as table
        </summary>
        <div className="mt-3">{table}</div>
      </details>
    </div>
  );
}

/** One named analysis: question, scope, result, provenance and caveats. Presentational only. */
export function AnalysisDetailView({ analysis }: { analysis: Analysis }) {
  const state = analysisState(analysis);
  const prov = analysis.provenance;
  const listing = analysis.op === "filter_rows";
  const base = analysis.denominator
    ? `${formatNumber(analysis.denominator.value)} ${analysis.denominator.label}`
    : listing
      ? prov.rows_matched != null
        ? `${formatNumber(prov.rows_matched)} matching records; ${formatNumber(analysis.rows.length)} shown`
        : "Matching records, one per row"
      : "Shown per row: each group has its own base";
  const scope = [
    { label: "Question", value: analysis.question },
    {
      label: "Filters",
      value: analysis.filters.length > 0 ? analysis.filters.map(describeFilter).join(" · ") : "None: all records in the dataset",
    },
    {
      label: "Grouped by",
      value: analysis.group_by.length > 0 ? analysis.group_by.map(humanizeKey).join(", ") : listing ? "Not grouped: one row per record" : "Not grouped",
    },
    { label: "Base", value: base },
    { label: "Unit", value: listing ? "As labelled in each column" : unitLabel(analysis.unit) },
    { label: "Category", value: categoryLabel(analysis.category) },
  ];

  return (
    <div className="flex flex-col">
      <Section title="What was measured">
        <Card padding="sm">
          <KeyValueList items={scope} columns={2} />
        </Card>
      </Section>

      <Section
        title="Result"
        description={state.kind === "computed" ? "Recomputed from the dataset each time this page loads." : undefined}
      >
        {state.kind === "computed" ? (
          <section
            aria-label="Computed result"
            className="rounded-lg border border-border border-l-[3px] border-l-cite-result bg-surface p-4"
          >
            <p className="mb-3 text-xs font-medium text-cite-result">Computed from structured data</p>
            {analysis.rows.length > 0 ? (
              <ResultBody analysis={analysis} />
            ) : (
              <p className="text-base text-secondary">The analysis ran but matched no rows.</p>
            )}
          </section>
        ) : (
          <Callout tone={state.kind === "mismatch" ? "warn" : "neutral"} title={state.kind === "mismatch" ? "Result changed since curation; numbers withheld" : "This dataset is not currently available"}>
            {state.message}
          </Callout>
        )}
      </Section>

      <Section title="Provenance">
        <Card padding="sm">
          <KeyValueList
            columns={2}
            items={[
              { label: "Dataset", value: prov.source_title },
              { label: "Version", value: `Version ${prov.version}` },
              { label: "Table", value: tableLabel(prov.table) },
              { label: "Rows matched", value: prov.rows_matched != null ? formatNumber(prov.rows_matched) : "-" },
              { label: "Recomputed at", value: formatDateTime(prov.computed_at) },
            ]}
          />
        </Card>
      </Section>

      <Section title="Caveats">
        {analysis.caveats.length > 0 ? (
          <ul className="flex list-disc flex-col gap-1.5 pl-5 text-base text-secondary">
            {analysis.caveats.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        ) : (
          <p className="text-base text-muted">No caveats recorded for this analysis.</p>
        )}
      </Section>

      <div className="mt-8">
        <DevDetails data={{ analysis_id: analysis.id, operation: analysis.op, dataset: prov.dataset, source_code: prov.source_code, spec: analysis.spec }} />
      </div>
    </div>
  );
}
