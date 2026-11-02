/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Sign-in was removed; keep old links working.
  async redirects() {
    return [
      { source: "/login", destination: "/account", permanent: false },
      // The site lives at deal-intelligence.app; the old vercel.app addresses forward there, path and query kept.
      ...["deal-intelligence-app.vercel.app", "deal-intelligence-zeta.vercel.app"].map((host) => ({
        source: "/:path*",
        has: [{ type: "host", value: host }],
        destination: "https://deal-intelligence.app/:path*",
        permanent: true,
      })),
    ];
  },
};

export default nextConfig;
