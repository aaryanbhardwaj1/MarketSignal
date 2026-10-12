import type { EvidenceChild } from "@/lib/api/types";
import { cx } from "@/lib/cx";
import { segmentHighlight } from "@/lib/highlight";

/** Indexed segments of a passage; choosing one highlights it (choosing it again clears it). */
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
  if (spans.length === 0) return <p className="text-sm text-muted">No indexed segments.</p>;
  const ordered = [...spans].sort((a, b) => a.ordinal - b.ordinal);

  return (
    <ul className="flex flex-col gap-1.5">
      {ordered.map((c, index) => {
        const active = c.child_id === activeId;
        const preview = segmentHighlight(text, c.char_start, c.char_end).mark;
        return (
          <li key={c.child_id}>
            <button
              type="button"
              aria-pressed={active}
              onClick={() => onSelect(active ? null : c.child_id)}
              className={cx(
                "w-full rounded-md border px-3 py-2 text-left text-sm",
                active ? "border-accent bg-accent-subtle" : "border-border bg-surface hover:bg-surface-muted",
              )}
            >
              <span className="block text-xs font-medium text-muted">
                Segment {index + 1}
                {active && " · highlighted"}
              </span>
              <span className="mt-0.5 line-clamp-2 block text-primary">{preview || "(empty segment)"}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
