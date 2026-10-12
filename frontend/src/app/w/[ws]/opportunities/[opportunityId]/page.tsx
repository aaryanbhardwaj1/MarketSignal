import { OpportunityDetail } from "@/components/opportunities/opportunity-detail";

export default async function Page({ params }: PageProps<"/w/[ws]/opportunities/[opportunityId]">) {
  const { ws, opportunityId } = await params;
  return <OpportunityDetail ws={ws} opportunityId={opportunityId} />;
}
