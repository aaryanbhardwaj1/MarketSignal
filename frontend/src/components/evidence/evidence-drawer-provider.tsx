"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useMemo, useState, type ReactNode } from "react";
import { businessLocator } from "@/lib/format";
import { Drawer } from "../ui/drawer";
import { EvidenceDrawerContext, type EvidenceDrawerApi } from "./drawer-context";
import { drawerHref, parseDrawerParams, type DrawerTarget } from "./drawer-params";
import { EvidenceDrawerBody, useEvidencePassage, type SpanHint } from "./evidence-drawer";
import { ResultDetail } from "./result-detail";

export { useEvidenceDrawer, useOptionalEvidenceDrawer } from "./drawer-context";
export type { EvidenceDrawerApi, OpenEvidenceInput } from "./drawer-context";

function currentSearch(): string {
  return typeof window === "undefined" ? "" : window.location.search;
}

/**
 * Owns the single evidence/result drawer for a workspace. State lives in the URL (`?ev=&child=`
 * or `?res=`), so deep links and the back button work; opening pushes a history entry and
 * closing replaces it.
 */
export function EvidenceDrawerProvider({ ws, children }: { ws: string; children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname() ?? "/";
  const [hint, setHint] = useState<SpanHint | null>(null);

  const go = useCallback(
    (target: DrawerTarget | null, mode: "push" | "replace") => {
      const href = drawerHref(pathname, currentSearch(), target);
      if (mode === "push") router.push(href, { scroll: false });
      else router.replace(href, { scroll: false });
    },
    [pathname, router],
  );

  const api = useMemo<EvidenceDrawerApi>(
    () => ({
      openEvidence: ({ handle, childId = null, charStart, charEnd, quote }) => {
        const trimmed = handle.trim();
        if (!trimmed) return;
        setHint({ handle: trimmed, childId: childId ?? null, charStart, charEnd, quote });
        go({ kind: "evidence", handle: trimmed, childId: childId ?? null }, "push");
      },
      openResult: (resultId) => {
        if (resultId.trim()) go({ kind: "result", resultId: resultId.trim() }, "push");
      },
      close: () => go(null, "replace"),
    }),
    [go],
  );

  const selectChild = useCallback(
    (handle: string, childId: string | null) => go({ kind: "evidence", handle, childId }, "replace"),
    [go],
  );

  return (
    <EvidenceDrawerContext.Provider value={api}>
      {children}
      <Suspense fallback={null}>
        <DrawerHost ws={ws} hint={hint} onClose={api.close} onSelectChild={selectChild} />
      </Suspense>
    </EvidenceDrawerContext.Provider>
  );
}

function DrawerHost({
  ws,
  hint,
  onClose,
  onSelectChild,
}: {
  ws: string;
  hint: SpanHint | null;
  onClose: () => void;
  onSelectChild: (handle: string, childId: string | null) => void;
}) {
  const params = useSearchParams();
  const target = params ? parseDrawerParams(params) : null;
  const evidence = target?.kind === "evidence" ? target : null;
  // Shares the body's query (same key), so the subtitle costs no extra request.
  const passage = useEvidencePassage(ws, evidence?.handle ?? "", evidence?.childId ?? null);

  return (
    <Drawer
      open={target !== null}
      onClose={onClose}
      title={target?.kind === "result" ? "Computed result" : "Evidence passage"}
      subtitle={evidence && passage.data ? businessLocator(passage.data.locator_label) || undefined : undefined}
    >
      {evidence && (
        <EvidenceDrawerBody
          key={evidence.handle}
          ws={ws}
          handle={evidence.handle}
          childId={evidence.childId}
          hint={hint && hint.handle === evidence.handle ? hint : null}
          onSelectChild={(childId) => onSelectChild(evidence.handle, childId)}
        />
      )}
      {target?.kind === "result" && <ResultDetail ws={ws} resultId={target.resultId} />}
    </Drawer>
  );
}
