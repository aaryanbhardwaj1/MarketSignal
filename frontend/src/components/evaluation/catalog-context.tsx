"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { EvalCatalog } from "@/lib/api/contracts";

const CatalogContext = createContext<EvalCatalog | null>(null);

/** Makes the loaded catalog available to source tooltips (sha256 and git lookups). */
export function CatalogProvider({ catalog, children }: { catalog: EvalCatalog; children: ReactNode }) {
  return <CatalogContext.Provider value={catalog}>{children}</CatalogContext.Provider>;
}

export function useCatalogContext(): EvalCatalog | null {
  return useContext(CatalogContext);
}
