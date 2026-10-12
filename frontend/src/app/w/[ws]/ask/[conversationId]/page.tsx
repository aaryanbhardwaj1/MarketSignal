import type { Metadata } from "next";
import { ConversationView } from "@/components/ask/conversation-view";

export const metadata: Metadata = { title: "Conversation · Ask MarketSignal" };

export default async function AskConversationPage({ params }: PageProps<"/w/[ws]/ask/[conversationId]">) {
  const { ws, conversationId } = await params;
  return <ConversationView ws={ws} conversationId={conversationId} />;
}
