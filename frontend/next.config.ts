import type { NextConfig } from "next";

const BACKEND = process.env.BACKEND_URL || "http://localhost:8000";

// For the unified Render deployment we statically export the app and serve it
// from the FastAPI backend (same origin), so /api/* and /auth/* hit the backend
// directly — no rewrites needed. For local `next dev` we keep rewrites that
// proxy to a separately-running backend on :8000.
const isExport = process.env.NEXT_OUTPUT_EXPORT === "true";
// GitHub Pages project sites live under /<repo>/ — set NEXT_PUBLIC_BASE_PATH
// (e.g. "/fed-watcher") at build time so assets and data fetches resolve.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig: NextConfig = isExport
  ? {
      output: "export",
      images: { unoptimized: true },
      trailingSlash: true,
      ...(basePath ? { basePath } : {}),
    }
  : {
      async rewrites() {
        return [
          { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
          { source: "/auth/:path*", destination: `${BACKEND}/auth/:path*` },
          { source: "/admin-secure-panel/api/:path*", destination: `${BACKEND}/admin-secure-panel/api/:path*` },
        ];
      },
    };

export default nextConfig;
