import { AskFrame } from "@/components/ask/ask-frame";
import { AskSessionProvider } from "@/components/ask/ask-session";

export default async function AskLayout({ children, params }: LayoutProps<"/w/[ws]/ask">) {
  const { ws } = await params;
  return (
    <AskSessionProvider ws={ws}>
      <AskFrame>{children}</AskFrame>
    </AskSessionProvider>
  );
}
