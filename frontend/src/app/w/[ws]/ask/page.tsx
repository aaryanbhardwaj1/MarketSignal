import type { Metadata } from "next";
import { AskIntro } from "@/components/ask/ask-intro";

export const metadata: Metadata = { title: "Ask MarketSignal" };

export default async function AskPage({ params }: PageProps<"/w/[ws]/ask">) {
  const { ws } = await params;
  return <AskIntro ws={ws} />;
}
