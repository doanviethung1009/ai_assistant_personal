"use server";

import { requireSession, type ActionAuthCode } from "@/lib/auth-guard";
import { revalidatePath } from "next/cache";
import { wipeAllDataApi } from "@/lib/api";
import type { WipeOptions } from "@/lib/store/types";
import { deleteVaultAction } from "./vault-actions";

export async function wipeAllDataAction(
  options?: WipeOptions & { vault?: boolean },
): Promise<{ ok: boolean; error?: string; code?: ActionAuthCode }> {
  const auth = await requireSession();
  if (!auth.ok) return auth;
  try {
    await wipeAllDataApi(options);
    if (!options || options.vault) {
      await deleteVaultAction();
    }
    revalidatePath('/', 'layout');
    return { ok: true };
  } catch (error) {
    // Chỉ log tên lỗi; client nhận câu chung (không lộ chi tiết nội bộ).
    console.error("xoá dữ liệu thất bại", error instanceof Error ? error.name : "unknown");
    return { ok: false, error: "Xoá dữ liệu thất bại. Kiểm tra DATA_SOURCE và log của web." };
  }
}
