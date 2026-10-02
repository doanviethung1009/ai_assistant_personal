"use server";

import { scrapeChromeHistory, listChromeProfiles } from "@/lib/chrome-history";
import { revalidatePath } from "next/cache";

/**
 * Trích xuất lịch sử Chrome và lưu vào file JSON trong thư mục data.
 * Hỗ trợ đường dẫn tuỳ chỉnh hoặc tự detect theo OS.
 */
export async function syncChromeHistoryAction(limit: number = 2000, customPath?: string) {
  try {
    const res = await scrapeChromeHistory(limit, customPath || undefined);
    revalidatePath("/history");
    revalidatePath("/data");
    return { ok: true, count: res.count, path: res.savedPath };
  } catch (error: any) {
    return { ok: false, error: error.message || String(error) };
  }
}

/**
 * Liệt kê tất cả Chrome profile trên máy (tên hiển thị, email, đường dẫn).
 * Dùng để hiển thị dropdown cho user chọn profile cần cào lịch sử.
 */
export async function listChromeProfilesAction() {
  try {
    const profiles = await listChromeProfiles();
    return { ok: true, profiles };
  } catch (error: any) {
    return { ok: false, error: error.message || String(error), profiles: [] };
  }
}
