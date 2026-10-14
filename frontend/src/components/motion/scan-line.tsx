import { cx } from "@/lib/cx";

/**
 * Restrained scanning effect for retrieval: a 2px track with a short accent segment sweeping
 * across. Place it at the top or bottom edge of the region being searched. Decorative when no
 * `label` is given (pair it with a visible status line).
 */
export function ScanLine({ active = true, label, className }: { active?: boolean; label?: string; className?: string }) {
  return (
    <div
      role={label ? "progressbar" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      aria-busy={label ? active : undefined}
      className={cx("relative h-0.5 w-full overflow-hidden rounded-full bg-sunken", className)}
    >
      {active && (
        <span
          className="ms-scan absolute inset-y-0 left-0 w-full"
          style={{ background: "linear-gradient(90deg, transparent 0%, transparent 35%, var(--color-accent) 50%, transparent 65%, transparent 100%)" }}
        />
      )}
    </div>
  );
}
