import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Cần cho image prod gọn, chỉ copy runtime tối thiểu
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    // Next 15 mặc định KHÔNG giữ cache client cho page động (dynamic = 0), nên mỗi lần bấm menu đều
    // render lại ở server và gọi core qua tunnel. Giữ page đã xem 30 giây trong Router Cache của
    // browser: quay lại trang cũ hiện ngay, 0 request. Mutation đi qua Server Action đã gọi
    // revalidatePath (actions.ts: revalidateAll) nên xoá cache này; thay đổi từ ngoài (Jira sync nền)
    // chậm tối đa 30 giây, cùng bậc với TTL 10 giây của core-cache.
    staleTimes: { dynamic: 30, static: 180 },
    // Cho phép Server Action nhận payload lớn hơn mặc định 1MB
    serverActions: {
      bodySizeLimit: "100mb",
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
