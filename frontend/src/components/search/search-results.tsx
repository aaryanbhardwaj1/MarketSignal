import Link from "next/link";
import type { SearchHit } from "@/lib/api/types";
import { evidenceViewerHref } from "@/lib/handles";
import { Badge } from "../ui/badge";

function formatScore(score: number): string {
  return Number.isFinite(score) ? score.toFixed(4) : String(score);
}

export function SearchResults({ ws, hits }: { ws: string; hits: SearchHit[] }) {
  if (hits.length === 0) return <p className="text-sm text-slate-500">No hits.</p>;
  return (
    <ol className="flex flex-col gap-3" aria-label="Search results">
      {hits.map((hit) => (
        <li key={`${hit.rank}-${hit.child_id}`}>
          <Link
            href={evidenceViewerHref(ws, hit.handle, hit.child_id)}
            className="block rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-indigo-300 hover:shadow-md focus-visible:outline-2 focus-visible:outline-indigo-600"
          >
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="grid h-6 min-w-6 place-items-center rounded bg-slate-900 px-1.5 font-semibold text-white">
                {hit.rank}
              </span>
              <span className="font-mono tabular-nums text-slate-500">score {formatScore(hit.score)}</span>
              <span className="font-mono font-semibold text-indigo-700">{hit.source_code}</span>
              <span className="text-slate-700">{hit.source_title}</span>
              <Badge tone="neutral">{hit.source_class}</Badge>
              <Badge tone="muted">{hit.child_kind}</Badge>
              <span className="text-slate-600">{hit.locator_label}</span>
            </div>
            <p className="mt-2 line-clamp-4 whitespace-pre-wrap break-words text-sm text-slate-700">
              {hit.snippet}
            </p>
            <p className="mt-2 break-all font-mono text-xs text-slate-400">
              {hit.handle} [{hit.char_start}, {hit.char_end})
            </p>
          </Link>
        </li>
      ))}
    </ol>
  );
}
