import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, className }: { href: string; children: unknown; className?: string }) => (
    <a href={href} className={className}>
      {children as never}
    </a>
  ),
}));

import catalogJson from "@/lib/api/__fixtures__/evaluation-catalog.json";
import type { EvalCatalog } from "@/lib/api/contracts";
import { formatNumber } from "@/lib/format";
import { FailuresTab, failureBucketLabel } from "./failures-tab";

const catalog = catalogJson as unknown as EvalCatalog;
const html = renderToStaticMarkup(<FailuresTab catalog={catalog} ws="NORTHSTAR" />);
const textOf = (s: string) => s.replace(/<[^>]+>/g, " ").replace(/&#x27;/g, "'").replace(/&amp;/g, "&");

describe("FailuresTab", () => {
  it("uses plain labels for known bucket ids and humanises unknown ones", () => {
    expect(failureBucketLabel("both_miss")).toBe("Missed by both lanes");
    expect(failureBucketLabel("task_type_wrong")).toBe("Routed to the wrong task type");
    expect(failureBucketLabel("some_new_bucket")).toBe("Some new bucket");
    const text = textOf(html);
    for (const run of catalog.failure_runs) for (const b of run.buckets) expect(text).toContain(failureBucketLabel(b.id));
    expect(text).not.toContain(">both_miss<");
  });

  it("lists one row per run and bucket, linking to the run view filtered to that bucket", () => {
    for (const run of catalog.failure_runs) {
      for (const b of run.buckets) {
        expect(html).toContain(`/runs/${run.run_id}?bucket=${b.id}`);
        expect(textOf(html)).toContain(`${formatNumber(b.n)} of ${formatNumber(run.item_count)}`);
      }
    }
    const table = html.slice(html.indexOf("Failure buckets per evaluation run"));
    const rows = table.match(/<tr[ >]/g)?.length ?? 0;
    const expected = catalog.failure_runs.reduce((sum, r) => sum + Math.max(r.buckets.length, 1), 0);
    expect(rows - 1).toBe(expected); // minus the header row
  });

  it("charts the first run with failures as bars of stored bucket counts", () => {
    const first = catalog.failure_runs.find((r) => r.buckets.length > 0)!;
    expect(html).toContain(`aria-label="Items per failure bucket, ${first.label}"`);
    for (const b of first.buckets) expect(html).toContain(`${failureBucketLabel(b.id)}: ${formatNumber(b.n)}`);
  });
});
