import type { Metadata } from "next";
import { DeckBuilder } from "@/components/deck/deck-builder";
import { parseDeckSelection } from "@/lib/views/insights";

export const metadata: Metadata = { title: "Create presentation" };

/** Query values as `URLSearchParams` (a repeated key keeps its first value). */
function toParams(query: Record<string, string | string[] | undefined>): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    const first = Array.isArray(value) ? value[0] : value;
    if (first !== undefined) params.set(key, first);
  }
  return params;
}

export default async function Page({ params, searchParams }: PageProps<"/w/[ws]/insights/deck">) {
  const { ws } = await params;
  const selection = parseDeckSelection(toParams(await searchParams));
  return <DeckBuilder ws={ws} initial={selection} />;
}
