"use client";

import type { ReactNode } from "react";
import { PageContainer } from "@/components/ui/page-container";
import { RunAnnouncer } from "./run-announcer";

/**
 * Chat layout: one reading column. Conversation history lives in the shell's sidebar, so this
 * frame only sets the column width and hosts the run announcer.
 */
export function AskFrame({ children }: { children: ReactNode }) {
  return (
    <div className="min-w-0">
      <PageContainer width="reading" className="mx-auto">{children}</PageContainer>
      <RunAnnouncer />
    </div>
  );
}
