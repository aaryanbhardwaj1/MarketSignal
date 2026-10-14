import { redirect } from "next/navigation";
import { overviewRedirectTarget } from "@/components/shell/routes";

/** The former Overview is now Insights. */
export default async function OverviewRedirect({ params }: PageProps<"/w/[ws]/overview">) {
  const { ws } = await params;
  redirect(overviewRedirectTarget(ws));
}
