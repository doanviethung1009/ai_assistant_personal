import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Cần cho image prod gọn, chỉ copy runtime tối thiểu
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    // Cho phép Server Action nhận payload lớn hơn mặc định 1MB
    serverActions: {
      bodySizeLimit: "2mb",
    },
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};

export default nextConfig;
