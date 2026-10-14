import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lets parallel local dev servers (e.g. design reviews on different ports) use separate build
  // directories; the default is unchanged.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // Entry and legacy routes answer with a real 307 before rendering. The page stubs under app/
  // keep the same mapping as a fallback (components/shell/routes.ts).
  redirects() {
    return [
      { source: "/w/:ws", destination: "/w/:ws/ask", permanent: false },
      { source: "/w/:ws/overview", destination: "/w/:ws/insights", permanent: false },
      {
        source: "/w/:ws/chat",
        has: [{ type: "query", key: "c", value: "(?<c>[0-9A-Fa-f-]{8,64})" }],
        destination: "/w/:ws/ask/:c",
        permanent: false,
      },
      { source: "/w/:ws/chat", destination: "/w/:ws/ask", permanent: false },
      { source: "/w/:ws/sources", destination: "/w/:ws/evidence", permanent: false },
      {
        source: "/w/:ws/sources/:sourceId",
        destination: "/w/:ws/evidence/sources/:sourceId",
        permanent: false,
      },
      { source: "/w/:ws/search", destination: "/w/:ws/evidence", permanent: false },
    ];
  },
};

export default nextConfig;
