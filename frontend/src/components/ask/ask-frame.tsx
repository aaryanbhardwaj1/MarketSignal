"use client";

import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { PageContainer } from "@/components/ui/page-container";
import { cx } from "@/lib/cx";
import { ConversationPanel } from "./conversation-panel";

const PANEL_ID = "ask-conversations";

/**
 * Ask layout: a 17rem conversation panel beside the reading column. Under 1280px the panel
 * collapses behind a "Conversations" button and closes again after navigating.
 */
export function AskFrame({ ws, children }: { ws: string; children: ReactNode }) {
  const pathname = usePathname();
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  return (
    <div className="xl:flex">
      <aside
        id={PANEL_ID}
        aria-label="Saved conversations"
        className={cx(
          "border-border bg-surface xl:sticky xl:top-0 xl:flex xl:h-dvh xl:w-68 xl:shrink-0 xl:flex-col xl:border-b-0 xl:border-r",
          open ? "flex max-h-[70dvh] flex-col border-b" : "hidden",
        )}
      >
        <ConversationPanel ws={ws} />
      </aside>
      <div className="min-w-0 flex-1">
        <div className="px-4 pt-4 md:px-6 xl:hidden">
          <Button
            variant="secondary"
            size="sm"
            aria-expanded={open}
            aria-controls={PANEL_ID}
            onClick={() => setOpenOn(open ? null : pathname)}
          >
            {open ? "Hide conversations" : "Conversations"}
          </Button>
        </div>
        <PageContainer width="reading">{children}</PageContainer>
      </div>
    </div>
  );
}
