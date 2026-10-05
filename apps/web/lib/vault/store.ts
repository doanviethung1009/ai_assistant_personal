import "server-only";

import { mkdir, readFile, rename, writeFile, unlink } from "node:fs/promises";
import path from "node:path";

import { isVaultBlob, type VaultBlob } from "./crypto";

/**
 * Lưu blob đã mã hoá của Két xuống `data/vault.json`.
 *
 * Tách file riêng, KHÔNG nhét vào builder-data.json, vì:
 *   - Độc lập với DATA_SOURCE: dù web chạy file, memory hay api (Postgres),
 *     két vẫn nằm ở một chỗ, không phải migrate qua lại giữa các chế độ.
 *   - Có thể sao lưu, xoá, hoặc loại khỏi backup chung riêng biệt.
 *
 * Server chỉ thấy ciphertext. Dù lộ file này, kẻ tấn công vẫn phải brute-force
 * mật khẩu master qua PBKDF2 600k vòng.
 */

const MAX_BLOB_BYTES = 5 * 1024 * 1024;

function dataDir(): string {
  return process.env.DATA_DIR
    ? path.resolve(process.env.DATA_DIR)
    : path.resolve(process.cwd(), "..", "..", "data");
}

export function vaultFilePath(): string {
  return path.join(dataDir(), "vault.json");
}

// Memory mode: DATA_SOURCE=memory không được ghi đĩa
const globalCache = globalThis as typeof globalThis & {
  __vaultMemoryBlob?: VaultBlob | null;
};

function isMemoryMode(): boolean {
  return process.env.DATA_SOURCE === "memory";
}

// Tuần tự hoá ghi, cùng lý do với json-file.ts
let writeChain: Promise<unknown> = Promise.resolve();

export async function readVaultBlob(): Promise<VaultBlob | null> {
  if (isMemoryMode()) return globalCache.__vaultMemoryBlob ?? null;
  try {
    const raw = await readFile(vaultFilePath(), "utf8");
    const parsed: unknown = JSON.parse(raw);
    return isVaultBlob(parsed) ? parsed : null;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}

export class VaultConflictError extends Error {
  constructor() {
    super(
      "Két đã được sửa ở nơi khác (tab khác?). Tải lại trang rồi mở khoá lại.",
    );
  }
}

/**
 * Ghi blob mới. `expectedUpdatedAt` là updated_at của blob client đã đọc:
 * nếu khác bản trên server thì từ chối, tránh tab cũ ghi đè mất mục mới.
 * Truyền null khi tạo két lần đầu (chưa có blob nào).
 */
export function writeVaultBlob(
  blob: VaultBlob,
  expectedUpdatedAt: string | null,
): Promise<void> {
  const job = async () => {
    const current = await readVaultBlob();
    if ((current?.updated_at ?? null) !== expectedUpdatedAt) {
      throw new VaultConflictError();
    }

    if (isMemoryMode()) {
      globalCache.__vaultMemoryBlob = blob;
      return;
    }

    const target = vaultFilePath();
    await mkdir(path.dirname(target), { recursive: true });
    const body = JSON.stringify(blob);
    if (Buffer.byteLength(body) > MAX_BLOB_BYTES) {
      throw new Error("Két quá lớn (giới hạn 5MB).");
    }
    const tmp = `${target}.tmp`;
    // mode 0600: chỉ chủ sở hữu đọc được, tránh user khác trên máy đọc
    await writeFile(tmp, body, { encoding: "utf8", mode: 0o600 });
    try {
      await rename(target, `${target}.bak`);
    } catch {
      // lần ghi đầu tiên
    }
    await rename(tmp, target);
  };

  const next = writeChain.then(job, job);
  writeChain = next.catch(() => undefined);
  return next;
}

export async function readVaultRaw(): Promise<string | null> {
  const blob = await readVaultBlob();
  return blob ? JSON.stringify(blob, null, 2) : null;
}

export async function deleteVaultBlob(): Promise<void> {
  if (isMemoryMode()) {
    globalCache.__vaultMemoryBlob = null;
    return;
  }
  const target = vaultFilePath();
  try {
    await unlink(target);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
      throw error;
    }
  }
}
