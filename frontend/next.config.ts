import type { NextConfig } from "next";

const BACKEND = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
      { source: "/auth/:path*", destination: `${BACKEND}/auth/:path*` },
      { source: "/admin-secure-panel/api/:path*", destination: `${BACKEND}/admin-secure-panel/api/:path*` },
    ];
  },
};

export default nextConfig;
