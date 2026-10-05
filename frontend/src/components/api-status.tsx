"use client";

import { useEffect, useState } from "react";

type Status = "checking" | "ready" | "degraded" | "not_ready" | "unreachable";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const STYLES: Record<Status, string> = {
  checking: "bg-zinc-100 text-zinc-600",
  ready: "bg-emerald-100 text-emerald-800",
  degraded: "bg-amber-100 text-amber-800",
  not_ready: "bg-red-100 text-red-800",
  unreachable: "bg-red-100 text-red-800",
};

/** Polls the API readiness endpoint so local setup problems are visible immediately. */
export function ApiStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await fetch(`${API_URL}/readyz`, { cache: "no-store" });
        const body: { status?: Status } = await res.json();
        if (!cancelled) setStatus(body.status ?? "not_ready");
      } catch {
        if (!cancelled) setStatus("unreachable");
      }
    };
    void check();
    const timer = setInterval(check, 10_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return (
    <span className={`rounded-full px-3 py-1 text-sm font-medium ${STYLES[status]}`}>
      API: {status.replace("_", " ")}
    </span>
  );
}
