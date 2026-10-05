export function ContextExcerpts({
  previous,
  next,
}: {
  previous: string | null;
  next: string | null;
}) {
  const block = (label: string, text: string | null, position: "before" | "after") => (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      {text ? (
        <p className="mt-1 whitespace-pre-wrap break-words text-sm text-slate-500">
          {position === "before" ? "..." : ""}
          {text}
          {position === "after" ? "..." : ""}
        </p>
      ) : (
        <p className="mt-1 text-sm italic text-slate-400">None (start or end of source)</p>
      )}
    </div>
  );
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {block("Previous excerpt", previous, "before")}
      {block("Next excerpt", next, "after")}
    </div>
  );
}
