import { Suspense } from "react";
import { ChatView } from "@/components/chat/chat-view";
import { Loading } from "@/components/ui/loading";

export default async function ChatPage({ params }: PageProps<"/w/[ws]/chat">) {
  const { ws } = await params;
  // ChatView reads ?c= with useSearchParams (it rewrites the URL itself via history.replaceState).
  return (
    <Suspense fallback={<Loading label="Loading chat..." />}>
      <ChatView ws={ws} />
    </Suspense>
  );
}
