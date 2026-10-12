import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Gallery } from "./gallery";

export const metadata: Metadata = { title: "Design gallery", robots: { index: false } };

/** Developer-only gallery of every design-system primitive and state. 404 in production. */
export default async function DevDesignPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  if (process.env.NODE_ENV === "production") notFound();
  const { open } = await searchParams;
  const overlay = open === "drawer" || open === "dialog" ? open : undefined;
  return <Gallery initialOverlay={overlay} />;
}
