import { redirect } from "next/navigation";
import { connection } from "next/server";
import { rootRedirectTarget } from "@/components/shell/routes";
import { listWorkspaces } from "@/lib/api/endpoints";

const LOOKUP_TIMEOUT_MS = 2_000;

/** `/` opens Chat in NORTHSTAR, or in the first visible workspace when NORTHSTAR is absent. */
export default async function Home() {
  await connection(); // resolve at request time, never at build time
  let workspaces: { code: string }[] | null = null;
  try {
    workspaces = await listWorkspaces(AbortSignal.timeout(LOOKUP_TIMEOUT_MS));
  } catch {
    workspaces = null; // API unreachable: fall back to the default workspace
  }
  redirect(rootRedirectTarget(workspaces));
}
