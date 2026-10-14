import type { ReactNode } from "react";
import { cx } from "@/lib/cx";

/**
 * Height animation without measuring (CSS grid rows, 200ms). Closed content is `inert`, so it
 * leaves the tab order and the accessibility tree.
 */
export function Collapse({ open, id, className, children }: { open: boolean; id?: string; className?: string; children: ReactNode }) {
  return (
    <div id={id} data-open={open ? "true" : "false"} className={cx("ms-collapse", className)} inert={!open}>
      <div>{children}</div>
    </div>
  );
}
