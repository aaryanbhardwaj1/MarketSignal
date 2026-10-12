import { integrity as integrityLabel, isTabularSource } from "@/lib/labels";
import { businessLocator, parseRowPassage } from "@/lib/format";
import { cx } from "@/lib/cx";
import { Badge } from "./badge";
import { RowFields } from "./row-fields";
import type { Integrity } from "@/lib/api/contracts";

/**
 * One evidence passage: source line, business locator ("Page 4", "Row 43"), the passage and its
 * role and integrity. Parser internals (blocks, versions) are not shown here. Spreadsheet and
 * CSV rows render as labelled fields rather than a quote of the serialized row.
 * `source.version` is accepted for callers but not shown (it belongs in Technical details).
 */
export function EvidenceCard({
  source,
  locator,
  quote,
  role,
  integrity,
  onOpen,
}: {
  source: { title: string; type: string; classLabel: string; version?: string | number };
  locator: string;
  quote: string;
  role?: "support" | "contradict";
  integrity?: Integrity;
  onOpen?: () => void;
}) {
  const integ = integrity ? integrityLabel(integrity) : null;
  const where = businessLocator(locator);
  const fields = isTabularSource(source.type) ? parseRowPassage(quote) : null;
  return (
    <article className="rounded-lg border border-border bg-surface p-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-base font-medium text-primary">{source.title}</h3>
          <p className="mt-0.5 text-sm text-muted">
            {[source.classLabel, source.type, where].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-1.5">
          {role && <Badge tone={role === "support" ? "neutral" : "warn"}>{role === "support" ? "Supports" : "Contradicts"}</Badge>}
          {integ && integrity !== "verified" && <Badge tone={integ.tone}>{integ.label}</Badge>}
        </div>
      </header>
      {fields ? (
        <RowFields
          fields={fields}
          className={cx("mt-3 border-l-2 pl-3", role === "contradict" ? "border-warn" : "border-border-strong")}
        />
      ) : (
        <blockquote
          className={cx(
            "mt-3 border-l-2 pl-3 text-base text-secondary",
            role === "contradict" ? "border-warn" : "border-border-strong",
          )}
        >
          {quote}
        </blockquote>
      )}
      {onOpen && (
        <button
          type="button"
          onClick={onOpen}
          className="mt-3 rounded-sm text-sm font-medium text-accent-text hover:underline"
        >
          Open passage
        </button>
      )}
    </article>
  );
}
