import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",   // pure static HTML — no Node.js server needed
  trailingSlash: true, // /login → /login/index.html for static hosting
};

export default nextConfig;
