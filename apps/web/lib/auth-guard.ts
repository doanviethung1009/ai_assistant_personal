import "server-only";

import { authEnabled } from "./auth-config";
import { classifyCoreError } from "./core-errors";
import { hasPermission, type Permission } from "./permissions";
import { getSessionUser } from "./session";

/**
 * Guard cho Server Action. Server Action là endpoint HTTP CÔNG KHAI (client gửi được body tuỳ ý
 * kể cả không đi qua UI), nên MỌI action phải mở đầu bằng `const auth = await requireSession()` hoặc
 * `requirePermission(...)` rồi `if (!auth.ok) return auth;`. tests/server-actions-guard.test.ts đỏ
 * nếu quên. Lớp phòng thủ khác: coreFetch không phiên thì không gọi core, và core đòi JWT.
 */
export type ActionAuthCode = "unauthenticated" | "forbidden" | "session_expired" | "error";

/** Kết quả thất bại, tương thích kiểu `{ ok: false; error?: string }` của mọi action. */
export interface AuthFailure {
  ok: false;
  code: ActionAuthCode;
  error: string;
}

export interface AuthSuccess {
  ok: true;
  user: { uid: string; local: boolean };
}

export type AuthResult = AuthSuccess | AuthFailure;

const MESSAGES: Record<ActionAuthCode, string> = {
  unauthenticated: "Phiên đăng nhập đã hết hạn. Tải lại trang để đăng nhập lại.",
  session_expired: "Phiên đăng nhập đã bị thu hồi. Tải lại trang để đăng nhập lại.",
  forbidden: "Bạn không có quyền thực hiện thao tác này",
  error: "Không kiểm tra được quyền. Thử lại sau.",
};

function fail(code: ActionAuthCode): AuthFailure {
  return { ok: false, code, error: MESSAGES[code] };
}

/** Chế độ cục bộ (file/memory): không đăng nhập, mọi quyền mở (spec 4.10). */
const LOCAL_SUCCESS: AuthSuccess = { ok: true, user: { uid: "local", local: true } };

/**
 * Có phiên hợp lệ. Chỉ giải mã cookie, KHÔNG gọi core (core tự kiểm quyền ghi theo chủ).
 */
export async function requireSession(): Promise<AuthResult> {
  if (!authEnabled()) return LOCAL_SUCCESS;
  const session = await getSessionUser();
  if (!session) return fail("unauthenticated");
  return { ok: true, user: { uid: session.uid, local: false } };
}

/**
 * Có phiên và có quyền `permission`. Một lời gọi /me (React.cache nên chung với layout), để chặn
 * sớm trước khi làm việc tốn kém như tải URL hay parse file. Core vẫn là bên quyết định.
 */
export async function requirePermission(permission: Permission): Promise<AuthResult> {
  const base = await requireSession();
  if (!base.ok || base.user.local) return base;
  try {
    // Import lười: lib/api import lib/session; tránh vòng và tránh nạp store cục bộ khi không cần.
    const { getMe } = await import("./api");
    const me = await getMe();
    return hasPermission(me.permissions, permission) ? base : fail("forbidden");
  } catch (error) {
    return toActionAuthError(error) ?? fail("error");
  }
}

/**
 * Đổi lỗi core thành kết quả auth cho action, hoặc null nếu không phải lỗi phiên/quyền
 * (action tự xử lý như cũ). 401/403 không `code` là sai cấu hình, không phải hết phiên.
 */
export function toActionAuthError(error: unknown): AuthFailure | null {
  switch (classifyCoreError(error)) {
    case "unauthenticated":
      return fail("unauthenticated");
    case "session_expired":
      return fail("session_expired");
    case "forbidden":
      return fail("forbidden");
    case "config":
      return { ok: false, code: "error", error: "Cấu hình web→core sai. Báo quản trị viên." };
    default:
      return null;
  }
}

/**
 * Cho Server Component: người xem có quyền `permission` không, để KHÔNG gọi endpoint bị cấm
 * (đỡ một lời gọi 403) và hiện ForbiddenPanel. Dùng chung getMe (React.cache) với layout. Lỗi khác
 * (core sập, phiên hỏng) trả true để luồng thường gặp lại lỗi đó và hiện đúng panel; core vẫn là
 * bên quyết định.
 */
export async function canView(permission: Permission): Promise<boolean> {
  if (!authEnabled()) return true;
  try {
    const { getMe } = await import("./api");
    return hasPermission((await getMe()).permissions, permission);
  } catch {
    return true;
  }
}
