// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Table, type Column } from "./table";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

type Row = { id: string; name: string };
const COLUMNS: Column<Row>[] = [
  { key: "name", header: "Name", cell: (r) => r.name },
  { key: "open", header: "Link", cell: () => <a href="#x">Open</a> },
];

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

function press(target: Element, key: string): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  act(() => {
    target.dispatchEvent(event);
  });
  return event;
}

describe("Table row activation", () => {
  it("activates from the row itself, but not from a link inside it", () => {
    const onRowClick = vi.fn();
    act(() => root.render(<Table caption="c" columns={COLUMNS} rows={[{ id: "a", name: "A" }]} rowKey={(r) => r.id} onRowClick={onRowClick} />));
    const row = host.querySelector("tbody tr") as HTMLTableRowElement;
    const link = host.querySelector("tbody a") as HTMLAnchorElement;

    const onLink = press(link, "Enter");
    expect(onRowClick).not.toHaveBeenCalled();
    expect(onLink.defaultPrevented).toBe(false);

    act(() => link.click());
    expect(onRowClick).not.toHaveBeenCalled();

    press(row, "Enter");
    expect(onRowClick).toHaveBeenCalledTimes(1);
    act(() => (row.querySelector("td") as HTMLElement).click());
    expect(onRowClick).toHaveBeenCalledTimes(2);
  });
});
