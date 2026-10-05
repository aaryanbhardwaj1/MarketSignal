import type { SourceVersion } from "@/lib/api/types";
import { Badge } from "../ui/badge";

/** Warnings that change how a version can be retrieved get a friendlier label. */
const WARNING_LABELS: Record<string, { label: string; title: string }> = {
  EMBEDDER_UNAVAILABLE: {
    label: "lexical-only",
    title: "EMBEDDER_UNAVAILABLE: no dense vectors were written; only lexical search covers this version.",
  },
};

export function WarningBadges({ warnings }: { warnings: readonly string[] | null | undefined }) {
  if (!warnings || warnings.length === 0) return <span className="text-slate-400">-</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {warnings.map((w) => {
        const known = WARNING_LABELS[w];
        return (
          <Badge key={w} tone="warning" title={known?.title ?? w}>
            {known?.label ?? w}
          </Badge>
        );
      })}
    </span>
  );
}

export function HealthBadge({ health }: { health: SourceVersion["health"] }) {
  if (!health) return <span className="text-slate-400">-</span>;
  const detail = [
    typeof health.checked === "number" ? `${health.checked} checked` : null,
    health.reason ? String(health.reason) : null,
  ]
    .filter(Boolean)
    .join("; ");
  return health.ok ? (
    <Badge tone="success" title={detail || undefined}>
      ok
    </Badge>
  ) : (
    <Badge tone="danger" title={detail || undefined}>
      failing
    </Badge>
  );
}

export function VersionError({ version }: { version: SourceVersion | null }) {
  if (!version?.error_code) return <span className="text-slate-400">-</span>;
  return (
    <span className="flex max-w-xs flex-col gap-0.5">
      <code className="font-mono text-xs font-semibold text-red-700">{version.error_code}</code>
      {version.error_detail && (
        <span className="whitespace-pre-wrap break-words text-xs text-slate-600">
          {version.error_detail}
        </span>
      )}
    </span>
  );
}
