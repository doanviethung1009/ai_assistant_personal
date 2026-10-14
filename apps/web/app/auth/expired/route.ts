import { signOut } from "@/auth";
import { authEnabled, readAuthConfig } from "@/lib/auth-config";

export const dynamic = "force-dynamic";

/**
 * Điểm đến khi core báo phiên bị thu hồi/khoá (token_invalid, user_inactive). Phải xoá cookie
 * TRƯỚC khi về /login, nếu không middleware thấy cookie còn hạn và đẩy về "/" → vòng lặp.
 * GET có chủ đích (Q12): bị dụ bấm link chỉ bị đăng xuất, không lộ hay ghi dữ liệu.
 * Chế độ file/memory không có đăng nhập → về "/".
 */
export async function GET(): Promise<Response> {
  if (!authEnabled() || !readAuthConfig().ok) {
    return new Response(null, { status: 302, headers: { Location: "/" } });
  }
  await signOut({ redirect: false });
  return new Response(null, { status: 302, headers: { Location: "/login?error=session" } });
}
