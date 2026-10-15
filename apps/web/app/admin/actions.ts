"use server";

import { revalidatePath } from "next/cache";

import {
  createLocalUserApi,
  deleteUserApi,
  inviteGoogleUserApi,
  resetUserPasswordApi,
  revokeUserSessionsApi,
  setUserAliasesApi,
  unlockUserApi,
  updateAdminUserApi,
} from "@/lib/api";
import { requirePermission, toActionAuthError } from "@/lib/auth-guard";
import { CoreApiError } from "@/lib/core-errors";
import { USER_ROLES, type AliasItem, type UserAdminUpdate, type UserRole } from "@/lib/types";

/**
 * Server Action quản trị người dùng (spec admin-users-local-login 5.5). Server Action là endpoint HTTP
 * CÔNG KHAI nên MỌI hàm mở đầu bằng requirePermission("user:manage") (test tĩnh bắt quên), rồi validate
 * input trước khi gọi core. Core vẫn là bên quyết định cuối (last_admin, self_lockout, env_admin...).
 *
 * ══════════════════════════════════════════════════════════════════════
 *  MẬT KHẨU TẠM chỉ được trả trong kết quả của createLocalUserAction / resetPasswordAction, cho
 *  client component hiển thị đúng một lần. Không log, không đưa vào URL, không revalidate kèm giá trị,
 *  không lưu ở bất kỳ đâu phía web. Không dùng console.* với dữ liệu form hay kết quả.
 * ══════════════════════════════════════════════════════════════════════
 */

export type AdminFailure = { ok: false; code?: string; error: string };
export type AdminResult<T extends object = object> = ({ ok: true } & T) | AdminFailure;

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const USERNAME_RE = /^[a-z0-9][a-z0-9._-]{2,63}$/;
const CONTROL_RE = /[\x00-\x1f\x7f]/;
const MAX_ALIASES = 20;

/** Thông báo cho mã lỗi nghiệp vụ của core. `alias_taken` dùng detail của core (có email người giữ). */
const CODE_MESSAGES: Record<string, string> = {
  self_lockout: "Không thể tự hạ quyền, tự khoá hoặc tự xoá chính mình.",
  last_admin: "Phải còn ít nhất một quản trị viên đang hoạt động.",
  env_admin: "Tài khoản này nằm trong ADMIN_EMAILS (cấu hình), không hạ quyền, khoá hay xoá được ở đây.",
  self_action: "Không đặt lại mật khẩu của chính mình ở đây. Dùng trang Đổi mật khẩu.",
  not_local_account: "Thao tác này chỉ áp dụng cho tài khoản nội bộ.",
  email_exists: "Email này đã được dùng.",
  username_exists: "Tên đăng nhập này đã được dùng.",
  has_data: "Người dùng còn task hoặc ghi chú (kể cả trong thùng rác), không xoá được. Hãy khoá tài khoản thay vì xoá.",
  weak_password: "Mật khẩu không đạt yêu cầu.",
};

/** Đổi lỗi core thành kết quả cho client. Mã đặc biệt (phiên, quyền, đổi mật khẩu) đi qua toActionAuthError. */
function failure(error: unknown): AdminFailure {
  const authError = toActionAuthError(error);
  if (authError) return authError;
  if (error instanceof CoreApiError) {
    if (error.code === "alias_taken") return { ok: false, code: error.code, error: error.message.slice(0, 300) };
    if (error.code && CODE_MESSAGES[error.code]) return { ok: false, code: error.code, error: CODE_MESSAGES[error.code]! };
    if (error.status === 404) return { ok: false, code: "not_found", error: "Không tìm thấy người dùng." };
    if (error.status === 422) return { ok: false, code: "invalid", error: error.message.slice(0, 300) };
    if (error.status === 429) return { ok: false, code: "rate_limited", error: "Quá nhiều yêu cầu. Thử lại sau ít phút." };
  }
  // Không đưa error.message lạ (có thể chứa dữ liệu) ra client.
  return { ok: false, error: "Thao tác không thành công. Thử lại sau." };
}

function str(formData: FormData, key: string): string {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function validEmail(email: string): boolean {
  return email.length > 0 && email.length <= 320 && email.includes("@") && !CONTROL_RE.test(email) && !/\s/.test(email);
}

function validRole(role: string): role is UserRole {
  return (USER_ROLES as readonly string[]).includes(role);
}

function validName(name: string): boolean {
  return name.length <= 200 && !CONTROL_RE.test(name);
}

function bad(error: string): AdminFailure {
  return { ok: false, code: "invalid", error };
}

// ── Tạo / mời ───────────────────────────────────────────────────

/** Mời tài khoản Google theo email (trạng thái `invited` tới khi họ đăng nhập lần đầu). */
export async function inviteGoogleUserAction(formData: FormData): Promise<AdminResult> {
  const auth = await requirePermission("user:manage");
  if (!auth.ok) return auth;
  const email = str(formData, "email").toLowerCase();
  const role = str(formData, "role") || "member";
  const name = str(formData, "name");
  if (!validEmail(email)) return bad("Email không hợp lệ.");
  if (!validRole(role)) return bad("Vai trò không hợp lệ.");
  if (!validName(name)) return bad("Tên tối đa 200 ký tự, không chứa ký tự điều khiển.");
  try {
    await inviteGoogleUserApi({ email, role, ...(name ? { name } : {}) });
  } catch (error) {
    return failure(error);
  }
  revalidatePath("/admin/users");
  return { ok: true };
}

export interface CreatedLocalUser {
  username: string;
  email: string;
  /** Hiện MỘT lần ở client; xem cảnh báo đầu file. */
  temporaryPassword: string;
}

/** Tạo tài khoản nội bộ; core sinh mật khẩu tạm và chỉ trả một lần trong response này. */
export async function createLocalUserAction(formData: FormData): Promise<AdminResult<CreatedLocalUser>> {
  const auth = await requirePermission("user:manage");
  if (!auth.ok) return auth;
  const username = str(formData, "username").toLowerCase();
  const email = str(formData, "email").toLowerCase();
  const role = str(formData, "role") || "member";
  const name = str(formData, "name");
  if (!USERNAME_RE.test(username)) {
    return bad("Tên đăng nhập 3-64 ký tự: chữ thường, số, dấu . _ -, bắt đầu bằng chữ hoặc số.");
  }
  if (!validEmail(email)) return bad("Email không hợp lệ.");
  if (!validRole(role)) return bad("Vai trò không hợp lệ.");
  if (!validName(name)) return bad("Tên tối đa 200 ký tự, không chứa ký tự điều khiển.");
  let created;
  try {
    created = await createLocalUserApi({ username, email, role, ...(name ? { name } : {}) });
  } catch (error) {
    return failure(error);
  }
  revalidatePath("/admin/users");
  return { ok: true, username: created.user.username ?? username, email: created.user.email, temporaryPassword: created.temporary_password };
}

// ── Sửa / thao tác ─────────────────────────────────────────────────

/** Cho phép một tập trường cố định; trường lạ bị từ chối thay vì chuyển tiếp nguyên cho core. */
export async function updateUserAction(id: string, patch: UserAdminUpdate): Promise<AdminResult> {
  const auth = await requirePermission("user:manage");
  if (!auth.ok) return auth;
  if (typeof id !== "string" || !UUID_RE.test(id)) return bad("Mã người dùng không hợp lệ.");
  if (!patch || typeof patch !== "object") return bad("Dữ liệu không hợp lệ.");
  const clean: UserAdminUpdate = {};
  for (const [key, value] of Object.entries(patch)) {
    if (value === undefined) continue;
    switch (key) {
      case "role":
        if (typeof value !== "string" || !validRole(value)) return bad("Vai trò không hợp lệ.");
        clean.role = value;
        break;
      case "status":
        if (value !== "active" && value !== "disabled") return bad("Trạng thái không hợp lệ.");
        clean.status = value;
        break;
      case "name":
        if (typeof value !== "string" || !validName(value.trim())) return bad("Tên không hợp lệ.");
        clean.name = value.trim();
        break;
      case "email":
        if (typeof value !== "string" || !validEmail(value.trim().toLowerCase())) return bad("Email không hợp lệ.");
        clean.email = value.trim().toLowerCase();
        break;
      case "username":
        if (typeof value !== "string" || !USERNAME_RE.test(value.trim().toLowerCase())) return bad("Tên đăng nhập không hợp lệ.");
        clean.username = value.trim().toLowerCase();
        break;
      default:
        return bad("Trường không được phép sửa.");
    }
  }
  if (Object.keys(clean).length === 0) return bad("Không có thay đổi nào.");
  try {
    await updateAdminUserApi(id, clean);
  } catch (error) {
    return failure(error);
  }
  revalidatePath("/admin/users");
  return { ok: true };
}

export interface ResetPasswordResult {
  /** Hiện MỘT lần ở client; xem cảnh báo đầu file. */
  temporaryPassword: string;
}

/** Đặt lại mật khẩu tài khoản nội bộ: core tăng session_version (mọi phiên của họ chết) và trả mật khẩu tạm. */
export async function resetPasswordAction(id: string): Promise<AdminResult<ResetPasswordResult>> {
  const auth = await requirePermission("user:manage");
  if (!auth.ok) return auth;
  if (typeof id !== "string" || !UUID_RE.test(id)) return bad("Mã người dùng không hợp lệ.");
  let result;
  try {
    result = await resetUserPasswordApi(id);
  } catch (error) {
    return failure(error);
  }
  revalidatePath("/admin/users");
  return { ok: true, temporaryPassword: result.temporary_password };
}

export async function unlockUserAction(id: string): Promise<AdminResult> {
  const auth = await requirePermission("user:manage");
  if (!auth.ok) return auth;
  if (typeof id !== "string" || !UUID_RE.test(id)) return bad("Mã người dùng không hợp lệ.");
  try {
    await unlockUserApi(id);
  } catch (error) {
    return failure(error);
  }
  revalidatePath("/admin/users");
  return { ok: true };
}

export async function revokeSessionsAction(id: string): Promise<AdminResult> {
  const auth = await requirePermission("user:manage");
  if (!auth.ok) return auth;
  if (typeof id !== "string" || !UUID_RE.test(id)) return bad("Mã người dùng không hợp lệ.");
  try {
    await revokeUserSessionsApi(id);
  } catch (error) {
    return failure(error);
  }
  revalidatePath("/admin/users");
  return { ok: true };
}

export async function deleteUserAction(id: string): Promise<AdminResult> {
  const auth = await requirePermission("user:manage");
  if (!auth.ok) return auth;
  if (typeof id !== "string" || !UUID_RE.test(id)) return bad("Mã người dùng không hợp lệ.");
  try {
    await deleteUserApi(id);
  } catch (error) {
    return failure(error);
  }
  revalidatePath("/admin/users");
  return { ok: true };
}

/** Thay TOÀN BỘ alias Jira của người dùng (tối đa 20, không trùng, không ký tự điều khiển). */
export async function setAliasesAction(id: string, aliases: string[]): Promise<AdminResult> {
  const auth = await requirePermission("user:manage");
  if (!auth.ok) return auth;
  if (typeof id !== "string" || !UUID_RE.test(id)) return bad("Mã người dùng không hợp lệ.");
  if (!Array.isArray(aliases)) return bad("Danh sách alias không hợp lệ.");
  const clean: AliasItem[] = [];
  const seen = new Set<string>();
  for (const raw of aliases) {
    if (typeof raw !== "string") return bad("Danh sách alias không hợp lệ.");
    const alias = raw.trim();
    if (!alias) continue;
    if (alias.length > 200 || CONTROL_RE.test(alias)) return bad("Alias tối đa 200 ký tự, không chứa ký tự điều khiển.");
    if (seen.has(alias)) continue;
    seen.add(alias);
    clean.push({ source: "jira", alias });
  }
  if (clean.length > MAX_ALIASES) return bad(`Tối đa ${MAX_ALIASES} alias.`);
  try {
    await setUserAliasesApi(id, clean);
  } catch (error) {
    return failure(error);
  }
  revalidatePath("/admin/users");
  return { ok: true };
}
