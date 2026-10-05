import Link from "next/link";
import type { UploadSourceResult } from "@/lib/api/types";

export function UploadResultMessage({ ws, result }: { ws: string; result: UploadSourceResult }) {
  const href = `/w/${encodeURIComponent(ws)}/sources/${encodeURIComponent(result.source_id)}`;
  const link = (
    <Link href={href} className="font-mono font-semibold underline">
      {result.source_code}
    </Link>
  );

  if (!result.created) {
    return (
      <p role="status" className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">
        Already ingested (v{result.version}) as {link}
        {result.duplicate_of && result.duplicate_of !== result.source_code
          ? `, duplicate of ${result.duplicate_of}`
          : ""}
        . No new version was created.
      </p>
    );
  }
  return (
    <p role="status" className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
      Accepted {link} v{result.version} - status {result.status}. The table refreshes while it
      ingests.
    </p>
  );
}
