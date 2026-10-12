import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lets parallel local dev servers (e.g. design reviews on different ports) use separate build
  // directories; the default is unchanged.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
