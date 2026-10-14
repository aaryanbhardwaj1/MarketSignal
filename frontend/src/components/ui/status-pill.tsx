import { cx } from "@/lib/cx";

/** Qualitative evidence statuses for insights and growth opportunities. Never a numeric score. */
export type EvidenceStatus =
  | "strong_evidence"
  | "supported"
  | "emerging"
  | "mixed_evidence"
  | "needs_validation"
  | "needs_research";

export const EVIDENCE_STATUS_LABEL: Record<EvidenceStatus, string> = {
  strong_evidence: "Strong evidence",
  supported: "Supported",
  emerging: "Emerging",
  mixed_evidence: "Mixed evidence",
  needs_validation: "Needs validation",
  needs_research: "Needs validation",
};

const TONE: Record<EvidenceStatus, { pill: string; dot: string }> = {
  strong_evidence: { pill: "bg-status-strong-bg text-status-strong", dot: "bg-status-strong" },
  supported: { pill: "bg-status-supported-bg text-status-supported", dot: "bg-status-supported" },
  emerging: { pill: "bg-status-emerging-bg text-status-emerging", dot: "bg-status-emerging" },
  mixed_evidence: { pill: "bg-status-mixed-bg text-status-mixed", dot: "bg-status-mixed" },
  needs_validation: { pill: "bg-status-validation-bg text-status-validation", dot: "bg-status-validation" },
  needs_research: { pill: "bg-status-validation-bg text-status-validation", dot: "bg-status-validation" },
};

export function isEvidenceStatus(value: string): value is EvidenceStatus {
  return value in EVIDENCE_STATUS_LABEL;
}

/** Small dot + exact status label. The label always carries the meaning; the colour only echoes it. */
export function StatusPill({ status, className }: { status: EvidenceStatus; className?: string }) {
  const tone = TONE[status];
  return (
    <span
      data-status={status}
      className={cx(
        "inline-flex h-5 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2 text-xs font-medium",
        tone.pill,
        className,
      )}
    >
      <span aria-hidden className={cx("h-1.5 w-1.5 shrink-0 rounded-full", tone.dot)} />
      {EVIDENCE_STATUS_LABEL[status]}
    </span>
  );
}
