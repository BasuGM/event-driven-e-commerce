import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The e2e container's browser reaches the dev server as http://frontend:3000; without this,
  // Next blocks its dev-only resources (HMR, dev chunks) for that host and pages never hydrate.
  allowedDevOrigins: ["frontend"],
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
