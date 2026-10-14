"use server";

import { CoreApiError, setCurrentUsersApi, setDisplayTimezoneApi } from "@/lib/api";
import { revalidatePath } from "next/cache";

const MAX_OWNERS = 20;
const MAX_OWNER_LENGTH = 200;

export interface SetUsersResult {
  ok: boolean;
  error?: string;
}

/**
 * Lưu danh sách tên "của tôi". Server Action là endpoint công khai nên validate ở đây,
 * khớp giới hạn của backend (tối đa 20 tên, mỗi tên 1-200 ký tự) để PUT không bị 422.
 * Trả {ok,error} thay vì ném để component hiện được thông báo rõ ràng.
 */
export async function setCurrentUserAction(names: string[]): Promise<SetUsersResult> {
  if (!Array.isArray(names)) return { ok: false, error: "Danh sách tên không hợp lệ" };
  const clean: string[] = [];
  for (const raw of names) {
    if (typeof raw !== "string") return { ok: false, error: "Danh sách tên không hợp lệ" };
    // Ký tự điều khiển (kể cả xuống dòng) bị backend từ chối; chặn sớm để PUT không 422.
    if (/[\x00-\x1f\x7f]/.test(raw)) {
      return { ok: false, error: "Tên không được chứa ký tự điều khiển" };
    }
    const name = raw.trim();
    if (!name || clean.includes(name)) continue;
    if (name.length > MAX_OWNER_LENGTH) {
      return { ok: false, error: `Mỗi tên tối đa ${MAX_OWNER_LENGTH} ký tự` };
    }
    clean.push(name);
  }
  if (clean.length > MAX_OWNERS) return { ok: false, error: `Tối đa ${MAX_OWNERS} tên` };

  try {
    await setCurrentUsersApi(clean);
  } catch (error) {
    if (error instanceof CoreApiError) return { ok: false, error: error.message };
    console.error("lưu tên người dùng thất bại", error instanceof Error ? error.name : "unknown");
    return { ok: false, error: "Không lưu được cài đặt. Kiểm tra service api." };
  }
  revalidatePath("/", "layout"); // Cập nhật toàn bộ các trang (Hôm nay, Task, Team)
  return { ok: true };
}

// Chỉ ký tự có thể xuất hiện trong tên IANA (Asia/Ho_Chi_Minh, Etc/GMT+12, America/Port-au-Prince).
const TIMEZONE_NAME_RE = /^[A-Za-z0-9_+\-/]+$/;

/**
 * Lưu múi giờ hiển thị. null = về mặc định env. Validate sơ bộ ở đây vì Server Action là
 * endpoint công khai; backend (danh sách IANA) mới là nơi quyết định cuối cùng. Backend trả
 * 409 khi đang có lần nhập giữ khoá, message của nó được chuyển nguyên cho người dùng.
 */
export async function setDisplayTimezoneAction(tz: string | null): Promise<SetUsersResult> {
  if (tz !== null) {
    if (typeof tz !== "string" || tz.length < 1 || tz.length > 64 || !TIMEZONE_NAME_RE.test(tz)) {
      return { ok: false, error: "Tên múi giờ không hợp lệ (ví dụ Asia/Ho_Chi_Minh)" };
    }
  }
  try {
    await setDisplayTimezoneApi(tz);
  } catch (error) {
    if (error instanceof CoreApiError) return { ok: false, error: error.message };
    console.error("lưu múi giờ thất bại", error instanceof Error ? error.name : "unknown");
    return { ok: false, error: "Không lưu được cài đặt. Kiểm tra service api." };
  }
  // Layout giữ tz trong context nên phải làm mới cả cây, không chỉ một trang.
  revalidatePath("/", "layout");
  return { ok: true };
}
