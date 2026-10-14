import type { Metadata } from "next";
import { Suspense } from "react";
import { AskIntro } from "@/components/ask/ask-intro";
import { AskPrefillFromQuery } from "@/components/ask/ask-prefill";

export const metadata: Metadata = { title: "Ask MarketSignal" };

export default async function AskPage({ params }: PageProps<"/w/[ws]/ask">) {
  const { ws } = await params;
  return (
    <>
      <AskIntro ws={ws} />
      {/* `?q=` from "Investigate in Chat" / "Ask a follow-up": prefill only, never auto-send. */}
      <Suspense fallback={null}>
        <AskPrefillFromQuery />
      </Suspense>
    </>
  );
}
