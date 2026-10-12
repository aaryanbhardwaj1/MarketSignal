import { Suspense } from "react";
import { TelemetryDashboard } from "@/components/telemetry/telemetry-dashboard";
import { PageContainer } from "@/components/ui/page-container";
import { LoadingRegion, Skeleton } from "@/components/ui/states";

export default async function TelemetryPage({ params }: PageProps<"/w/[ws]/dev/telemetry">) {
  const { ws } = await params;
  return (
    <Suspense
      fallback={
        <PageContainer width="wide">
          <LoadingRegion label="Loading telemetry">
            <Skeleton height="20rem" />
          </LoadingRegion>
        </PageContainer>
      }
    >
      <TelemetryDashboard ws={ws} />
    </Suspense>
  );
}
