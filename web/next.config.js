/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  // API proxying moved to app/api/[[...path]]/route.ts with 5-min timeout
  // to avoid ECONNRESET on long-running dashboard (1-2 min).
};

module.exports = nextConfig;
