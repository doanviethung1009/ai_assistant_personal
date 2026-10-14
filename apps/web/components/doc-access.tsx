import type { ReactNode } from "react";

import { ApiErrorPanel } from "@/components/api-error";
import { authEnabled } from "@/lib/auth-config";
import { hasPermission } from "@/lib/permissions";

/**
 * Cổng cho trang tài liệu (đọc file, không gọi core). Middleware chỉ giải mã cookie nên user bị
 * khoá/thu hồi vẫn còn cookie hợp lệ tới 7 ngày: ở chế độ api gọi getMe() (React.cache, dùng chung
 * với layout nên KHÔNG thêm request) để core xác nhận phiên còn sống. Lỗi phiên → ApiErrorPanel lo
 * redirect /auth/expired; lỗi mạng → panel lỗi, không đăng xuất.
 * `canInfra` = có `system:read` (xem tài liệu hạ tầng, lib/doc-access.ts). Cục bộ: mọi thứ mở.
 */
export async function loadDocAccess(): Promise<{ error: ReactNode | null; canInfra: boolean }> {
  if (!authEnabled()) return { error: null, canInfra: true };
  try {
    const { getMe } = await import("@/lib/api");
    const me = await getMe();
    return { error: null, canInfra: hasPermission(me.permissions, "system:read") };
  } catch (error) {
    return { error: <ApiErrorPanel error={error} />, canInfra: false };
  }
}
