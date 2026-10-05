import { humanize } from "@/lib/format";
import { statusTone } from "@/lib/status";
import { Badge } from "../ui/badge";

export function CountList({
  counts,
  asStatus = false,
  empty = "None",
}: {
  counts: Record<string, number>;
  asStatus?: boolean;
  empty?: string;
}) {
  const entries = Object.entries(counts).sort(([, a], [, b]) => b - a);
  if (entries.length === 0) return <p className="text-sm text-slate-500">{empty}</p>;
  const total = entries.reduce((sum, [, n]) => sum + n, 0);

  return (
    <ul className="flex flex-col gap-2.5">
      {entries.map(([key, n]) => (
        <li key={key} className="flex items-center gap-3 text-sm">
          <span className="w-32 shrink-0">
            {asStatus ? <Badge tone={statusTone(key)}>{humanize(key)}</Badge> : <span className="capitalize text-slate-700">{humanize(key)}</span>}
          </span>
          <span className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100" aria-hidden>
            <span
              className="block h-full rounded-full bg-indigo-500"
              style={{ width: `${total ? (n / total) * 100 : 0}%` }}
            />
          </span>
          <span className="w-8 text-right font-medium tabular-nums text-slate-900">{n}</span>
        </li>
      ))}
    </ul>
  );
}
