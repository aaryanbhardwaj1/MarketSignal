import type { ReactNode } from "react";
import type { StatusTone } from "@/lib/status";

export type BadgeTone = StatusTone | "info" | "neutral";

const TONE_CLASSES: Record<BadgeTone, string> = {
  success: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
  warning: "bg-amber-50 text-amber-800 ring-amber-600/25",
  danger: "bg-red-50 text-red-800 ring-red-600/20",
  progress: "bg-sky-50 text-sky-800 ring-sky-600/20",
  muted: "bg-slate-100 text-slate-600 ring-slate-500/20",
  info: "bg-indigo-50 text-indigo-800 ring-indigo-600/20",
  neutral: "bg-white text-slate-700 ring-slate-300",
};

export function Badge({
  tone = "neutral",
  title,
  children,
}: {
  tone?: BadgeTone;
  title?: string;
  children: ReactNode;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}
