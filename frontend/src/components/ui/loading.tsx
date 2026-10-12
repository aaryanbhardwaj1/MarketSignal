import { LoadingRegion } from "./states";

/** @deprecated Use `<LoadingRegion>` (skeleton + polite live region). */
export function Loading({ label = "Loading" }: { label?: string }) {
  return <LoadingRegion label={label} lines={3} />;
}
