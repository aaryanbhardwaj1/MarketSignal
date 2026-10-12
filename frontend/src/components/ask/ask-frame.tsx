"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { PageContainer } from "@/components/ui/page-container";
import { cx } from "@/lib/cx";
import { ConversationPanel } from "./conversation-panel";
import { RunAnnouncer } from "./run-announcer";

const PANEL_ID = "ask-conversations";

/**
 * Ask layout: the reading column comes first in the DOM (so "Skip to main content" lands on the
 * answer or composer, and the page h1 precedes the panel's headings); the 17rem conversation
 * panel is placed to its left with CSS order from 1280px. Below that the panel collapses behind a
 * "Conversations" button, takes focus when opened, and closes again after navigating.
 */
export function AskFrame({ ws, children }: { ws: string; children: ReactNode }) {
  const pathname = usePathname();
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === pathname;
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.querySelector<HTMLElement>("a[href], button, input")?.focus();
  }, [open]);

  return (
    <div className="flex flex-col xl:flex-row">
      <div className="order-1 px-4 pt-4 md:px-6 xl:hidden">
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
      <div className="order-3 min-w-0 flex-1 xl:order-2">
        <PageContainer width="reading">{children}</PageContainer>
      </div>
      <aside
        ref={panelRef}
        id={PANEL_ID}
        aria-label="Saved conversations"
        className={cx(
          "order-2 border-border bg-surface xl:sticky xl:top-0 xl:order-1 xl:flex xl:h-dvh xl:w-68 xl:shrink-0 xl:flex-col xl:self-start xl:border-y-0 xl:border-r",
          open ? "mt-3 flex max-h-[70dvh] flex-col border-y xl:mt-0" : "hidden",
        )}
      >
        <ConversationPanel ws={ws} />
      </aside>
      <RunAnnouncer />
    </div>
  );
}
