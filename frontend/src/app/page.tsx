import { ApiStatus } from "@/components/api-status";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-16">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-semibold tracking-tight">MarketSignal</h1>
        <ApiStatus />
      </div>
      <p className="text-zinc-600">
        Evidence-grounded growth-strategy research. Every material claim resolves to an exact,
        immutable evidence handle.
      </p>
      <p className="text-sm text-zinc-500">
        Phase 0 scaffold — workspaces, sources and research chat arrive in later phases.
      </p>
    </main>
  );
}
