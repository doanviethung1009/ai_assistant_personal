"use server";

import { CoreApiError, setCurrentUsersApi } from "@/lib/api";
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
