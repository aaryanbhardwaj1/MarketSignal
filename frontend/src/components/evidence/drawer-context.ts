"use client";

import { createContext, useContext } from "react";

export interface OpenEvidenceInput {
  handle: string;
  childId?: string | null;
  /** Span offsets in the passage, used when no child id is known. */
  charStart?: number;
  charEnd?: number;
  /** The cited text, kept as a hint only (never trusted over the server text). */
  quote?: string;
}

export interface EvidenceDrawerApi {
  openEvidence: (input: OpenEvidenceInput) => void;
  openResult: (resultId: string) => void;
  close: () => void;
}

export const EvidenceDrawerContext = createContext<EvidenceDrawerApi | null>(null);

/** The drawer API; throws outside `EvidenceDrawerProvider`. */
export function useEvidenceDrawer(): EvidenceDrawerApi {
  const api = useContext(EvidenceDrawerContext);
  if (!api) throw new Error("useEvidenceDrawer must be used inside EvidenceDrawerProvider");
  return api;
}

/** The drawer API when a provider is mounted, else null (for components also rendered standalone). */
export function useOptionalEvidenceDrawer(): EvidenceDrawerApi | null {
  return useContext(EvidenceDrawerContext);
}
