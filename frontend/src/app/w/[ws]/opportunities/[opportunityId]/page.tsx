import type { Metadata } from "next";
import { OpportunityDetail } from "@/components/opportunities/opportunity-detail";

/** Static section title; detail pages refine it once their record loads. */
export const metadata: Metadata = { title: "Growth Opportunities" };

export default async function Page({ params }: PageProps<"/w/[ws]/opportunities/[opportunityId]">) {
  const { ws, opportunityId } = await params;
  return <OpportunityDetail ws={ws} opportunityId={opportunityId} />;
}
