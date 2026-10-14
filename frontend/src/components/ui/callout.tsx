import { CircleAlert, Info, TriangleAlert, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

const ICON: Record<CalloutTone, LucideIcon> = { info: Info, warn: TriangleAlert, danger: CircleAlert, neutral: Info };
const ICON_TONE: Record<CalloutTone, string> = {
  info: "text-info",
  warn: "text-warn",
  danger: "text-danger",
  neutral: "text-muted",
};
/** Quiet tinted surface with a hairline; the leading rule carries the tone. */
const SURFACE: Record<CalloutTone, string> = {
  info: "bg-info-subtle/70 border-info/15",
  warn: "bg-warn-subtle/70 border-warn/20",
  danger: "bg-danger-subtle/70 border-danger/20",
  neutral: "bg-surface-muted border-border",
};
const LABEL: Record<CalloutTone, string> = { info: "Note", warn: "Warning", danger: "Problem", neutral: "Note" };

type CalloutTone = "info" | "warn" | "danger" | "neutral";

/** Inline notice. The tone is also named for assistive tech, never only coloured. */
export function Callout({
  tone,
  title,
  children,
  action,
}: {
  tone: CalloutTone;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}) {
  const Icon = ICON[tone];
  return (
    <div role={tone === "danger" ? "alert" : "note"} className={cx("flex gap-2.5 rounded-lg border px-3.5 py-3", SURFACE[tone])}>
      <Icon aria-hidden size={16} strokeWidth={1.75} className={cx("mt-0.5 shrink-0", ICON_TONE[tone])} />
      <div className="min-w-0 flex-1">
        <p className="text-base font-medium text-primary">
          <span className="sr-only">{LABEL[tone]}: </span>
          {title}
        </p>
        {children && <div className="mt-0.5 text-sm text-secondary">{children}</div>}
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </div>
  );
}
