import type { EvidenceChild } from "@/lib/api/types";
import { segmentHighlight } from "@/lib/highlight";

export function ChildSpanList({
  text,
  spans,
  activeId,
  onSelect,
}: {
  text: string;
  spans: EvidenceChild[];
  activeId: string | null;
  onSelect: (childId: string | null) => void;
}) {
  if (spans.length === 0) return <p className="text-sm text-slate-500">No child spans.</p>;
  const ordered = [...spans].sort((a, b) => a.ordinal - b.ordinal);

  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-col gap-2">
        {ordered.map((c) => {
          const active = c.child_id === activeId;
          const preview = segmentHighlight(text, c.char_start, c.char_end).mark;
          return (
            <li key={c.child_id}>
              <button
                type="button"
                aria-pressed={active}
                onClick={() => onSelect(active ? null : c.child_id)}
                className={`w-full rounded-lg border px-3 py-2 text-left text-sm transition focus-visible:outline-2 focus-visible:outline-indigo-600 ${
                  active
                    ? "border-amber-400 bg-amber-50"
                    : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
                }`}
              >
                <span className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span className="font-semibold text-slate-800">#{c.ordinal}</span>
                  <span>{c.kind}</span>
                  <span className="font-mono tabular-nums">
                    [{c.char_start}, {c.char_end})
                  </span>
                </span>
                <span className="mt-1 line-clamp-2 block text-slate-700">{preview || "(empty span)"}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
