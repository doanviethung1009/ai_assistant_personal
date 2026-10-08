"use server";

import { setCurrentUsersApi } from "@/lib/api";
import { revalidatePath } from "next/cache";

const MAX_OWNERS = 20;
const MAX_OWNER_LENGTH = 200;

/**
 * Lưu danh sách tên "của tôi". Server Action là endpoint công khai nên validate ở đây,
 * khớp giới hạn của tham số `owner` backend (tối đa 20 tên, mỗi tên 1-200 ký tự) để
 * sau này truyền sang view=mine không bị 422.
 */
export async function setCurrentUserAction(names: string[]) {
  if (!Array.isArray(names)) throw new Error("Danh sách tên không hợp lệ");
  const clean: string[] = [];
  for (const raw of names) {
    if (typeof raw !== "string") throw new Error("Danh sách tên không hợp lệ");
    const name = raw.trim();
    if (!name || clean.includes(name)) continue;
    if (name.length > MAX_OWNER_LENGTH) {
      throw new Error(`Mỗi tên tối đa ${MAX_OWNER_LENGTH} ký tự`);
    }
    clean.push(name);
  }
  if (clean.length > MAX_OWNERS) throw new Error(`Tối đa ${MAX_OWNERS} tên`);

  await setCurrentUsersApi(clean);
  revalidatePath("/", "layout"); // Cập nhật toàn bộ các trang (Hôm nay, Task, Team)
}
