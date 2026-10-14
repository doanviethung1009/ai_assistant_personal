import "server-only";

import { cache } from "react";

import { auth } from "@/auth";
import { parseSessionClaims, type SessionUser } from "./session-claims";
import { authEnabled, readAuthConfig } from "./auth-config";

export type { SessionUser };

/**
 * Phiên hiện tại hoặc null. Chỉ giải mã cookie, KHÔNG gọi core. `React.cache`: một lần render chỉ
 * đọc một lần dù layout, trang và coreFetch cùng hỏi. Giá trị sai dạng coi như không có phiên.
 * Ở file/memory luôn null (không có đăng nhập).
 */
export const getSessionUser = cache(async (): Promise<SessionUser | null> => {
  if (!authEnabled() || !readAuthConfig().ok) return null;
  const session = await auth();
  return parseSessionClaims(session);
});
