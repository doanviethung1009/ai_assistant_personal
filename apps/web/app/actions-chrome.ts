"use server";

import { scrapeChromeHistory } from "@/lib/chrome-history";
import { revalidatePath } from "next/cache";

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
