"use client";

import { createContext, useContext } from "react";

/** Shared numbering for inline chips and the consolidated evidence / analytics lists. */
export interface ChipNumbering {
  evidenceNumber: ReadonlyMap<string, number>;
  resultNumber: ReadonlyMap<string, number>;
}

export const ChipNumberingContext = createContext<ChipNumbering | null>(null);

export function useChipNumbering(): ChipNumbering | null {
  return useContext(ChipNumberingContext);
}
