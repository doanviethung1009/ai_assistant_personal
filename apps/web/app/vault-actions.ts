"use server";

import { revalidatePath } from "next/cache";

import { isVaultBlob, type VaultBlob } from "@/lib/vault/crypto";
import {
  readVaultBlob,
  VaultConflictError,
  writeVaultBlob,
  deleteVaultBlob,
} from "@/lib/vault/store";

/**
 * Server Action cho Két. Chỉ chuyển blob đã mã hoá qua lại, KHÔNG BAO GIỜ
 * nhận mật khẩu hay plaintext. Không log nội dung blob.
 */

export async function getVaultBlobAction(): Promise<{
  ok: boolean;
  blob: VaultBlob | null;
  error?: string;
}> {
  try {
    return { ok: true, blob: await readVaultBlob() };
  } catch (error) {
    console.error("vault: đọc thất bại", error instanceof Error ? error.message : "");
    return { ok: false, blob: null, error: "Không đọc được file két." };
  }
}

export async function saveVaultBlobAction(
  blob: unknown,
  expectedUpdatedAt: string | null,
): Promise<{ ok: boolean; error?: string }> {
  if (!isVaultBlob(blob)) {
    return { ok: false, error: "Dữ liệu két không hợp lệ." };
  }
  try {
    await writeVaultBlob(blob, expectedUpdatedAt);
    return { ok: true };
  } catch (error) {
    if (error instanceof VaultConflictError) {
      return { ok: false, error: error.message };
    }
    console.error("vault: ghi thất bại", error instanceof Error ? error.message : "");
    return { ok: false, error: "Không ghi được file két." };
  }
}

export async function deleteVaultAction(): Promise<{ ok: boolean; error?: string }> {
  try {
    await deleteVaultBlob();
    revalidatePath("/vault");
    revalidatePath("/data");
    return { ok: true };
  } catch (error) {
    return { ok: false, error: "Lỗi xoá két." };
  }
}

const MAX_VAULT_UPLOAD_BYTES = 5 * 1024 * 1024;

/**
 * Nhập lại file sao lưu két (ciphertext). CHỈ có chế độ thay thế: blob đã mã
 * hoá không thể trộn với két hiện có vì hai két dùng hai khoá khác nhau.
 *
 * Không cần mật khẩu ở bước này, vì server không giải mã gì. Mật khẩu (hoặc
 * mã khôi phục) của file nhập sẽ được hỏi khi mở khoá ở trang /vault. Bản két
 * hiện tại được writeVaultBlob đổi tên thành vault.json.bak trước khi ghi đè.
 */
export async function importVaultAction(
  formData: FormData,
): Promise<{ ok: boolean; error?: string }> {
  const file = formData.get("file");
  if (!(file instanceof File) || file.size === 0) {
    return { ok: false, error: "Chưa chọn file" };
  }
  if (file.size > MAX_VAULT_UPLOAD_BYTES) {
    return { ok: false, error: "File vượt quá 5 MB" };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(await file.text());
  } catch {
    return { ok: false, error: "File không phải JSON hợp lệ" };
  }
  if (!isVaultBlob(parsed)) {
    return { ok: false, error: "Đây không phải file sao lưu két hợp lệ." };
  }

  try {
    const current = await readVaultBlob();
    if (current && formData.get("confirm") !== "yes") {
      return {
        ok: false,
        error: "Đã có két. Tick xác nhận ghi đè để tiếp tục.",
      };
    }
    await writeVaultBlob(parsed, current?.updated_at ?? null);
    revalidatePath("/data");
    revalidatePath("/vault");
    return { ok: true };
  } catch (error) {
    if (error instanceof VaultConflictError) {
      return { ok: false, error: error.message };
    }
    console.error("vault: nhập thất bại", error instanceof Error ? error.message : "");
    return { ok: false, error: "Không ghi được file két." };
  }
}
