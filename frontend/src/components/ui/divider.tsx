import { cx } from "@/lib/cx";

/**
 * Hairline separator. `inset` indents it to line up with padded content; `label` puts a small
 * caption in the middle of the line ("Supporting detail", "Older").
 */
export function Divider({ inset = false, label, className }: { inset?: boolean; label?: string; className?: string }) {
  if (!label) {
    return <hr className={cx("border-0 border-t border-border", inset && "mx-4", className)} />;
  }
  return (
    <div role="separator" aria-label={label} className={cx("flex items-center gap-3", inset && "mx-4", className)}>
      <span aria-hidden className="h-px flex-1 bg-border" />
      <span aria-hidden className="text-xs font-medium text-muted">
        {label}
      </span>
      <span aria-hidden className="h-px flex-1 bg-border" />
    </div>
  );
}
