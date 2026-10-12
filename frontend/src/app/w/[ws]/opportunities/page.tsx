import type { Metadata } from "next";
import { OpportunitiesList } from "@/components/opportunities/opportunities-list";

export const metadata: Metadata = { title: "Growth Opportunities" };

export default async function Page({ params }: PageProps<"/w/[ws]/opportunities">) {
  const { ws } = await params;
  return <OpportunitiesList ws={ws} />;
}
