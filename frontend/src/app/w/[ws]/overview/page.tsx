import { OverviewPage } from "@/components/overview/overview-page";

export default async function Page({ params }: PageProps<"/w/[ws]/overview">) {
  const { ws } = await params;
  return <OverviewPage ws={ws} />;
}
