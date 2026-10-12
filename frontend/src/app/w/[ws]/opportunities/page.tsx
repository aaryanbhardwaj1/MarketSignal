import { OpportunitiesList } from "@/components/opportunities/opportunities-list";

export default async function Page({ params }: PageProps<"/w/[ws]/opportunities">) {
  const { ws } = await params;
  return <OpportunitiesList ws={ws} />;
}
