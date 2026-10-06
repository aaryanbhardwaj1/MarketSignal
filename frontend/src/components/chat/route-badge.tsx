import { describeRoute } from "@/lib/run-mode";
import type { RunRoute } from "@/lib/run-stream";
import { Badge } from "../ui/badge";

/** Which mode answered this run and why (router decision or the user's explicit choice). */
export function RouteBadge({ route }: { route: RunRoute | null }) {
  const description = describeRoute(route);
  if (!route || !description) return null;
  const cues = route.cues.slice(0, 6);
  return (
    <p className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
      <Badge tone={description.tone}>{description.label}</Badge>
      {cues.length > 0 && (
        <span>
          cues:{" "}
          {cues.map((cue, i) => (
            <code key={`${cue}-${i}`} className="mr-1 rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px] text-slate-700">
              {cue}
            </code>
          ))}
        </span>
      )}
    </p>
  );
}
