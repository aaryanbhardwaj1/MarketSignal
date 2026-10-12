"use client";

import { Button } from "./button";

/** Cursor pagination control. Renders nothing when there is no further page. */
export function LoadMore({ hasMore, loading, onLoadMore, label = "Load more" }: { hasMore: boolean; loading: boolean; onLoadMore: () => void; label?: string }) {
  if (!hasMore) return null;
  return (
    <div className="flex justify-center py-3">
      <Button variant="secondary" size="sm" loading={loading} onClick={onLoadMore}>
        {loading ? "Loading" : label}
      </Button>
    </div>
  );
}
