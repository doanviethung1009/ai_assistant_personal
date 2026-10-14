import type { DefaultSession } from "next-auth";

/**
 * Mở rộng kiểu Auth.js. Phiên chỉ mang `uid` và `sv` (session_version của core); KHÔNG role,
 * email, access_token hay id_token. Role/quyền luôn lấy từ GET /me của core.
 */
declare module "next-auth" {
  interface User {
    uid?: string;
    sv?: number;
  }
  interface Session extends DefaultSession {
    uid?: string;
    sv?: number;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    uid?: string;
    sv?: number;
  }
}
