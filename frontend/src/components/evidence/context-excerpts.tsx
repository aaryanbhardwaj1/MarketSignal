/** Drops a partial first word (the excerpt was cut by characters) before the leading ellipsis. */
export function trimLeadingPartialWord(text: string): string {
  const at = text.search(/\s/);
  return at > 0 && at < text.length - 1 ? text.slice(at).trimStart() : text;
}

/** Drops a partial last word before the trailing ellipsis. */
export function trimTrailingPartialWord(text: string): string {
  const at = text.search(/\s\S*$/);
  return at > 0 ? text.slice(0, at).trimEnd() : text;
}

/** Text just before and after the passage, for reading context only. */
export function ContextExcerpts({ previous, next }: { previous: string | null; next: string | null }) {
  if (!previous && !next) return null;
  const block = (label: string, text: string) => (
    <div className="min-w-0">
      <p className="text-xs font-medium text-muted">{label}</p>
      <p className="mt-0.5 line-clamp-4 whitespace-pre-wrap break-words text-sm text-muted">{text}</p>
    </div>
  );
  return (
    <section aria-label="Surrounding context" className="flex flex-col gap-3 border-l-2 border-border pl-3">
      {previous && block("Before this passage", `…${trimLeadingPartialWord(previous)}`)}
      {next && block("After this passage", `${trimTrailingPartialWord(next)}…`)}
    </section>
  );
}
