import { BrandLockup } from "@/components/brand/brand-mark";
import { LinkButton } from "@/components/ui/button";

const TITLE = "Page not found";

/** Unmatched URLs anywhere in the app (outside a workspace shell): branded, calm, one way back. */
export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-6 text-center">
      <title>{`${TITLE} · MarketSignal`}</title>
      <BrandLockup />
      <div className="flex max-w-md flex-col gap-2">
        <h1 className="text-xl font-semibold text-primary">{TITLE}</h1>
        <p className="text-base text-secondary">This page does not exist, or the link is out of date.</p>
      </div>
      <LinkButton href="/">Go to Chat</LinkButton>
    </main>
  );
}
