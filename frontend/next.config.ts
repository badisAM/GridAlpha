import type { NextConfig } from "next";

// All /api/* calls are proxied to the FastAPI backend -> same-origin in the
// browser, no CORS round-trips. In Docker, API_INTERNAL_URL=http://api:8000.
const API = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  // Next >= 16.3: do not generate AGENTS.md / CLAUDE.md in the repo
  agentRules: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

export default nextConfig;
