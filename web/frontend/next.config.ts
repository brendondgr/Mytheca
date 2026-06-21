import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root to this app. Without it, an unrelated lockfile in a
  // parent directory makes Next infer the wrong root (build warning).
  turbopack: {
    root: import.meta.dirname,
  },
};

export default nextConfig;
