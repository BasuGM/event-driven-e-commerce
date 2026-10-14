import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The e2e container's browser reaches the dev server as http://frontend:3000; without this,
  // Next blocks its dev-only resources (HMR, dev chunks) for that host and pages never hydrate.
  allowedDevOrigins: ["frontend"],
  // Same-origin API: the browser calls /api/* on this server and Next proxies to Django, so the
  // session and CSRF cookies are first-party. (Server components call API_URL directly.)
  async rewrites() {
    const backend = process.env.API_URL ?? "http://localhost:8000"
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*/` }]
  },
  // Django URLs end in "/". Without this Next would 308 /api/cart/ -> /api/cart, and Django's
  // APPEND_SLASH can't redirect a POST.
  skipTrailingSlashRedirect: true,
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
