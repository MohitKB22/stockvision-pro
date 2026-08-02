/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Emits a self-contained server bundle with only the modules actually
  // imported — this is what the Docker runtime stage copies, and why the
  // production image is ~180 MB instead of ~1.1 GB.
  //
  // Skipped on Vercel: that platform builds its own output format and does not
  // consume .next/standalone, so leaving the mode on there is at best noise and
  // at worst a source of confusing build output. `VERCEL` is set by the builder.
  output: process.env.VERCEL ? undefined : "standalone",

  // Tree-shakes barrel imports so importing one icon does not pull the entire
  // library into the client bundle. lucide-react alone is ~1,500 modules;
  // without this it measurably inflates first load.
  experimental: {
    optimizePackageImports: ["lucide-react", "recharts", "date-fns", "@tanstack/react-table"],
  },

  // Source maps in production make a bundle trivially reversible and roughly
  // double the deploy artifact size. Errors are correlated by request ID instead.
  productionBrowserSourceMaps: false,
  poweredByHeader: false,

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "geolocation=(), microphone=(), camera=()" },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
