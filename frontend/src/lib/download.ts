/**
 * Browser file download helpers: save a Blob through a temporary object URL and anchor, and
 * read a safe file name from a `Content-Disposition` header.
 */

const SAFE_NAME = /[^A-Za-z0-9._-]+/g;
const MAX_NAME = 120;

/** The `filename` from a `Content-Disposition` header, reduced to `[A-Za-z0-9._-]`, never a
 * path or a hidden file; `fallback` when absent or empty after cleaning. */
export function filenameFromDisposition(header: string | null | undefined, fallback: string): string {
  const match = header ? /filename="?([^";\r\n]+)"?/i.exec(header) : null;
  const raw = match?.[1] ?? "";
  const base = raw.split(/[\\/]/).pop() ?? "";
  const clean = base.replace(SAFE_NAME, "-").replace(/^[.-]+/, "").slice(0, MAX_NAME);
  return clean || fallback;
}

/** Starts a download of `blob` as `filename`; the object URL is revoked right after. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    // Deferred so the browser has started the download before the URL goes away.
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
}
