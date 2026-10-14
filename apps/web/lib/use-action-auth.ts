"use client";

import { useCallback } from "react";

/**
 * Xử lý lỗi phiên của kết quả Server Action ở client: hết/thu hồi phiên thì chuyển sang
 * /auth/expired (xoá cookie rồi về /login). `forbidden` và lỗi khác để component tự hiện thông báo
 * như cũ. Gọi ngay sau `await action()`; trả true nếu đã chuyển trang.
 */
export function useActionAuth(): (result: { ok?: boolean; code?: string } | null | undefined) => boolean {
  return useCallback(
    (result) => {
      if (!result || result.ok) return false;
      if (result.code === "session_expired" || result.code === "unauthenticated") {
        // Điều hướng cứng: /auth/expired là route handler xoá cookie rồi 302; router.push (client
        // transition) có thể dùng RSC cache cũ và không xoá chắc cookie.
        window.location.assign("/auth/expired");
        return true;
      }
      return false;
    },
    [],
  );
}
