import type { ReactNode } from "react";
import { cx } from "@/lib/cx";
import { TONE_SURFACE } from "./tone";

const ICON: Record<CalloutTone, string> = { info: "i", warn: "!", danger: "!", neutral: "i" };
const ICON_TONE: Record<CalloutTone, string> = {
  info: "border-info text-info",
  warn: "border-warn text-warn",
  danger: "border-danger text-danger",
  neutral: "border-text-muted text-muted",
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
  return (
    <div
      role={tone === "danger" ? "alert" : "note"}
      className={cx("flex gap-3 rounded-lg border px-4 py-3", TONE_SURFACE[tone])}
    >
      <span
        aria-hidden
        className={cx(
          "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-xs font-semibold leading-none",
          ICON_TONE[tone],
        )}
      >
        {ICON[tone]}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-base font-medium text-primary">
          <span className="sr-only">{LABEL[tone]}: </span>
          {title}
        </p>
        {children && <div className="mt-0.5 text-base text-secondary">{children}</div>}
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </div>
  );
}
