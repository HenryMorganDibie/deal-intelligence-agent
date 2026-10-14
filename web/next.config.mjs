/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Sign-in was removed; keep old links working.
  async redirects() {
    return [
      { source: "/login", destination: "/app", permanent: false },
      { source: "/auth/:path*", destination: "/app", permanent: false },
    ];
  },
};

export default nextConfig;
