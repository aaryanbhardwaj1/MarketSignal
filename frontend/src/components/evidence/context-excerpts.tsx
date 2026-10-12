/** Text just before and after the passage, for reading context only. */
export function ContextExcerpts({ previous, next }: { previous: string | null; next: string | null }) {
  if (!previous && !next) return null;
  const block = (label: string, text: string, position: "before" | "after") => (
    <div className="min-w-0">
      <p className="text-xs font-medium text-muted">{label}</p>
      <p className="mt-0.5 line-clamp-4 whitespace-pre-wrap break-words text-sm text-muted">
        {position === "before" ? "..." : ""}
        {text}
        {position === "after" ? "..." : ""}
      </p>
    </div>
  );
  return (
    <section aria-label="Surrounding context" className="flex flex-col gap-3 border-l-2 border-border pl-3">
      {previous && block("Before this passage", previous, "before")}
      {next && block("After this passage", next, "after")}
    </section>
  );
}
