/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Minimal, self-contained production build for the Docker image --
  // see web/Dockerfile. No effect on `next dev`.
  output: "standalone",
};

module.exports = nextConfig;
