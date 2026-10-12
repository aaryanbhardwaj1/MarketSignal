import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Table, type Column } from "./table";

type Row = { id: string; name: string; n: number };
const COLUMNS: Column<Row>[] = [
  { key: "name", header: "Source", cell: (r) => r.name },
  { key: "n", header: "Passages", cell: (r) => r.n, align: "right" },
];

describe("Table", () => {
  it("always renders a caption (screen-reader only by default) and column headers", () => {
    const html = renderToStaticMarkup(
      <Table caption="Sources in this workspace" columns={COLUMNS} rows={[{ id: "a", name: "Survey", n: 4 }]} rowKey={(r) => r.id} />,
    );
    expect(html).toContain('<caption class="sr-only">Sources in this workspace</caption>');
    expect(html).toContain('<th scope="col"');
    expect(html).toContain("Survey");
    expect(html).toContain("text-right tabular-nums");
  });

  it("shows a visible caption on request", () => {
    const html = renderToStaticMarkup(
      <Table caption="Recent runs" showCaption columns={COLUMNS} rows={[]} rowKey={(r) => r.id} />,
    );
    expect(html).not.toContain('class="sr-only">Recent runs');
    expect(html).toContain("Recent runs");
  });

  it("renders the empty state across all columns when there are no rows", () => {
    const html = renderToStaticMarkup(
      <Table caption="Sources" columns={COLUMNS} rows={[]} rowKey={(r) => r.id} empty="No sources match these filters." />,
    );
    expect(html).toMatch(/colspan="2"/i);
    expect(html).toContain("No sources match these filters.");
    expect(html).not.toContain("Survey");
  });

  it("falls back to a default empty message", () => {
    const html = renderToStaticMarkup(<Table caption="Sources" columns={COLUMNS} rows={[]} rowKey={(r) => r.id} />);
    expect(html).toContain("Nothing to show yet.");
  });

  it("makes rows keyboard-focusable only when they are clickable", () => {
    const rows = [{ id: "a", name: "Survey", n: 4 }];
    const plain = renderToStaticMarkup(<Table caption="c" columns={COLUMNS} rows={rows} rowKey={(r) => r.id} />);
    const clickable = renderToStaticMarkup(
      <Table caption="c" columns={COLUMNS} rows={rows} rowKey={(r) => r.id} onRowClick={() => undefined} />,
    );
    expect(plain).not.toContain("tabindex");
    expect(clickable).toContain('tabindex="0"');
  });
});
