import Link from "next/link";
import type { SearchItem } from "@/lib/api/types";
import { evidenceViewerHref } from "@/lib/handles";
import { segmentHighlight } from "@/lib/highlight";
import { formatStageLine } from "@/lib/search";
import { Badge } from "../ui/badge";

/** Plain-text snippet; offsets are Unicode code points, so segmentHighlight does the slicing. */
function Snippet({ item }: { item: SearchItem }) {
  const { text, mark_start, mark_end, truncated_left, truncated_right } = item.snippet;
  const seg = segmentHighlight(text, mark_start, mark_end);
  return (
    <p className="mt-2 whitespace-pre-wrap break-words text-sm text-slate-700">
      {truncated_left && "… "}
      {seg.before}
      {seg.valid && <mark className="evidence-mark">{seg.mark}</mark>}
      {seg.after}
      {truncated_right && " …"}
    </p>
  );
}

export function SearchResults({ ws, items }: { ws: string; items: SearchItem[] }) {
  if (items.length === 0) return <p className="text-sm text-slate-500">No results.</p>;
  return (
    <ol className="flex flex-col gap-3" aria-label="Search results">
      {items.map((item) => (
        <li
          key={`${item.rank}-${item.anchor.child_id}`}
          className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
        >
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="grid h-6 min-w-6 place-items-center rounded bg-slate-900 px-1.5 font-semibold text-white">
              {item.rank}
            </span>
            <span className="text-sm font-medium text-slate-900">{item.source_title}</span>
            <Badge tone="neutral">{item.source_class}</Badge>
            <span className="text-slate-600">{item.locator_label}</span>
          </div>
          <Snippet item={item} />
          <p className="mt-2 font-mono text-xs text-slate-500">{formatStageLine(item.scores)}</p>
          <Link
            href={evidenceViewerHref(ws, item.handle, item.anchor.child_id)}
            className="mt-1 inline-block break-all font-mono text-xs text-indigo-700 hover:underline focus-visible:outline-2 focus-visible:outline-indigo-600"
          >
            {item.handle}
          </Link>
        </li>
      ))}
    </ol>
  );
}
