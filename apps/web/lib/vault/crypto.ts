/**
 * Mã hoá Két (Vault) bằng Web Crypto, CHẠY Ở TRÌNH DUYỆT.
 *
 * ══════════════════════════════════════════════════════════════════════
 *  Server không bao giờ thấy mật khẩu, mã khôi phục hay plaintext.
 *
 *  Server chỉ lưu một blob đục. Mất CẢ mật khẩu LẪN mã khôi phục thì không
 *  có cách nào lấy lại dữ liệu — đó là chủ ý, không phải thiếu sót.
 * ══════════════════════════════════════════════════════════════════════
 *
 * Mô hình khoá (v2) — "envelope encryption":
 *
 *   DEK  khoá dữ liệu AES-256 ngẫu nhiên, mã hoá nội dung két
 *   ├─ wrap bằng KEK_password  (PBKDF2 từ mật khẩu master)
 *   └─ wrap bằng KEK_recovery  (PBKDF2 từ mã khôi phục)
 *
 * Vì sao tách DEK khỏi mật khẩu: có hai cách mở cùng một DEK (mật khẩu hoặc
 * mã khôi phục) mà không phải mã hoá nội dung hai lần. Đổi mật khẩu hay dùng
 * mã khôi phục để đặt mật khẩu mới chỉ cần wrap lại DEK, nội dung giữ nguyên.
 *
 * AES-GCM vừa mã hoá vừa xác thực: sai mật khẩu/mã hoặc blob bị sửa đều làm
 * giải mã ném lỗi, nên không cần lưu "hash mật khẩu". Mỗi lần mã hoá dùng IV
 * 12 byte ngẫu nhiên mới; không bao giờ dùng lại IV với cùng khoá.
 *
 * v1 (cũ): khoá sinh thẳng từ mật khẩu, không có mã khôi phục. Vẫn mở được,
 * và được nâng lên v2 ở lần lưu kế tiếp.
 */

export const PBKDF2_ITERATIONS = 600_000;
/**
 * Mã khôi phục có 160 bit entropy ngẫu nhiên, brute-force bất khả thi dù
 * KDF yếu hơn. Giảm vòng lặp để mở khoá bằng mã không bị chậm vô ích.
 */
export const RECOVERY_ITERATIONS = 100_000;
export const MIN_PASSWORD_LENGTH = 10;

// Bảng chữ cái 32 ký tự, bỏ I/O/0/1 dễ nhầm khi chép tay hoặc đọc từ giấy
const RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

export interface WrappedKey {
  salt: string;
  iterations: number;
  iv: string;
  wrapped: string;
}

export interface VaultBlobV1 {
  v: 1;
  kdf: { name: "PBKDF2-SHA256"; iterations: number; salt: string };
  iv: string;
  ciphertext: string;
  updated_at: string;
}

export interface VaultBlobV2 {
  v: 2;
  iv: string;
  ciphertext: string;
  wraps: { password: WrappedKey; recovery: WrappedKey | null };
  updated_at: string;
}

export type VaultBlob = VaultBlobV1 | VaultBlobV2;

export interface VaultField {
  id: string;
  label: string;
  value: string;
  /** true thì bị che mặc định, chỉ hiện khi bấm "Hiện". */
  secret: boolean;
}

export interface VaultEntry {
  id: string;
  name: string;
  /** Loại hệ thống: database, server, api, cloud... Chuỗi tự do. */
  system_type: string;
  project: string;
  tags: string[];
  fields: VaultField[];
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface VaultPayload {
  entries: VaultEntry[];
}

/**
 * Trạng thái khi đã mở khoá. `dekRaw` giữ byte DEK để wrap lại khi đổi mật
 * khẩu; nó sống trong RAM cùng plaintext và bị bỏ khi khoá két.
 */
export interface VaultSession {
  dekRaw: Uint8Array<ArrayBuffer>;
  dek: CryptoKey;
  wraps: { password: WrappedKey; recovery: WrappedKey | null };
}

// ── base64 ────────────────────────────────────────────────────────────

function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function fromBase64(text: string): Uint8Array<ArrayBuffer> {
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

// ── Khoá ──────────────────────────────────────────────────────────────

async function deriveKek(
  secret: string,
  salt: Uint8Array<ArrayBuffer>,
  iterations: number,
): Promise<CryptoKey> {
  const material = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", hash: "SHA-256", salt, iterations },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

function importDek(raw: Uint8Array<ArrayBuffer>): Promise<CryptoKey> {
  // Không cho export: JS không đọc lại được byte khoá từ CryptoKey này
  return crypto.subtle.importKey("raw", raw, "AES-GCM", false, [
    "encrypt",
    "decrypt",
  ]);
}

async function wrapDek(
  dekRaw: Uint8Array<ArrayBuffer>,
  secret: string,
  iterations: number,
): Promise<WrappedKey> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const kek = await deriveKek(secret, salt, iterations);
  const wrapped = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, kek, dekRaw);
  return {
    salt: toBase64(salt),
    iterations,
    iv: toBase64(iv),
    wrapped: toBase64(new Uint8Array(wrapped)),
  };
}

async function unwrapDek(
  wrap: WrappedKey,
  secret: string,
): Promise<Uint8Array<ArrayBuffer>> {
  const kek = await deriveKek(secret, fromBase64(wrap.salt), wrap.iterations);
  try {
    const raw = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: fromBase64(wrap.iv) },
      kek,
      fromBase64(wrap.wrapped),
    );
    return new Uint8Array(raw);
  } catch {
    throw new WrongPasswordError();
  }
}

// ── Mã khôi phục ─────────────────────────────────────────────────────

/** 32 ký tự chia 8 nhóm 4, ví dụ `K7QM-2XPD-…`. 160 bit entropy. */
export function generateRecoveryKey(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  // 256 chia hết cho 32 nên `% 32` không bị lệch phân bố (không modulo bias)
  const chars = Array.from(bytes, (b) => RECOVERY_ALPHABET[b % 32]!);
  const groups: string[] = [];
  for (let i = 0; i < chars.length; i += 4) groups.push(chars.slice(i, i + 4).join(""));
  return groups.join("-");
}

/** Chuẩn hoá khi người dùng nhập: bỏ dấu gạch/khoảng trắng, viết hoa. */
export function normalizeRecoveryKey(input: string): string {
  return input.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

// ── Vòng đời két ─────────────────────────────────────────────────────

export class WrongPasswordError extends Error {
  constructor() {
    super("Sai mật khẩu (hoặc mã khôi phục), hoặc dữ liệu két đã bị sửa.");
  }
}

async function sessionFromDek(
  dekRaw: Uint8Array<ArrayBuffer>,
  wraps: VaultSession["wraps"],
): Promise<VaultSession> {
  return { dekRaw, dek: await importDek(dekRaw), wraps };
}

/** Tạo két mới: DEK ngẫu nhiên + mật khẩu + mã khôi phục (hiện một lần). */
export async function createVault(
  password: string,
): Promise<{ session: VaultSession; recoveryKey: string }> {
  const dekRaw = crypto.getRandomValues(new Uint8Array(32));
  const recoveryKey = generateRecoveryKey();
  const session = await sessionFromDek(dekRaw, {
    password: await wrapDek(dekRaw, password, PBKDF2_ITERATIONS),
    recovery: await wrapDek(
      dekRaw,
      normalizeRecoveryKey(recoveryKey),
      RECOVERY_ITERATIONS,
    ),
  });
  return { session, recoveryKey };
}

/** Sinh mã khôi phục mới. Mã cũ mất hiệu lực vì wrap cũ bị thay thế. */
export async function regenerateRecovery(
  session: VaultSession,
): Promise<{ session: VaultSession; recoveryKey: string }> {
  const recoveryKey = generateRecoveryKey();
  const next = await sessionFromDek(session.dekRaw, {
    password: session.wraps.password,
    recovery: await wrapDek(
      session.dekRaw,
      normalizeRecoveryKey(recoveryKey),
      RECOVERY_ITERATIONS,
    ),
  });
  return { session: next, recoveryKey };
}

/** Đặt mật khẩu mới, giữ nguyên DEK và mã khôi phục. */
export async function rewrapPassword(
  session: VaultSession,
  newPassword: string,
): Promise<VaultSession> {
  return sessionFromDek(session.dekRaw, {
    password: await wrapDek(session.dekRaw, newPassword, PBKDF2_ITERATIONS),
    recovery: session.wraps.recovery,
  });
}

export async function encryptPayload(
  session: VaultSession,
  payload: VaultPayload,
): Promise<VaultBlobV2> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encrypted = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    session.dek,
    new TextEncoder().encode(JSON.stringify(payload)),
  );
  return {
    v: 2,
    iv: toBase64(iv),
    ciphertext: toBase64(new Uint8Array(encrypted)),
    wraps: session.wraps,
    updated_at: new Date().toISOString(),
  };
}

async function decryptPayload(
  dek: CryptoKey,
  blob: Pick<VaultBlob, "iv" | "ciphertext">,
): Promise<VaultPayload> {
  try {
    const decrypted = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: fromBase64(blob.iv) },
      dek,
      fromBase64(blob.ciphertext),
    );
    const payload = JSON.parse(new TextDecoder().decode(decrypted)) as VaultPayload;
    if (!Array.isArray(payload.entries)) payload.entries = [];
    return payload;
  } catch {
    throw new WrongPasswordError();
  }
}

/** Mở khoá bằng mật khẩu. Hỗ trợ cả blob v1 (cũ) lẫn v2. */
export async function unlockBlob(
  password: string,
  blob: VaultBlob,
): Promise<{ session: VaultSession; payload: VaultPayload }> {
  if (blob.v === 1) {
    // Đường cũ: khoá sinh thẳng từ mật khẩu. Giải mã được thì nâng lên v2
    // ngay trong session (DEK mới), blob được ghi lại dạng v2 ở lần lưu sau.
    const key = await deriveKek(
      password,
      fromBase64(blob.kdf.salt),
      blob.kdf.iterations,
    );
    const payload = await decryptPayload(key, blob);
    const dekRaw = crypto.getRandomValues(new Uint8Array(32));
    const session = await sessionFromDek(dekRaw, {
      password: await wrapDek(dekRaw, password, PBKDF2_ITERATIONS),
      recovery: null,
    });
    return { session, payload };
  }

  const dekRaw = await unwrapDek(blob.wraps.password, password);
  const session = await sessionFromDek(dekRaw, blob.wraps);
  return { session, payload: await decryptPayload(session.dek, blob) };
}

/** Quên mật khẩu: mở bằng mã khôi phục rồi đặt luôn mật khẩu mới. */
export async function unlockWithRecovery(
  recoveryKey: string,
  newPassword: string,
  blob: VaultBlob,
): Promise<{ session: VaultSession; payload: VaultPayload }> {
  if (blob.v !== 2 || !blob.wraps.recovery) {
    throw new Error("Két này chưa có mã khôi phục.");
  }
  const dekRaw = await unwrapDek(
    blob.wraps.recovery,
    normalizeRecoveryKey(recoveryKey),
  );
  const opened = await sessionFromDek(dekRaw, blob.wraps);
  const payload = await decryptPayload(opened.dek, blob);
  return { session: await rewrapPassword(opened, newPassword), payload };
}

// ── Kiểm tra hình dạng ───────────────────────────────────────────────

function isWrappedKey(value: unknown): value is WrappedKey {
  if (typeof value !== "object" || value === null) return false;
  const w = value as Partial<WrappedKey>;
  return (
    typeof w.salt === "string" &&
    typeof w.iv === "string" &&
    typeof w.wrapped === "string" &&
    typeof w.iterations === "number" &&
    w.iterations >= 50_000 &&
    w.iterations <= 5_000_000
  );
}

/** Kiểm tra blob nhận từ server/đĩa trước khi đưa vào Web Crypto. */
export function isVaultBlob(value: unknown): value is VaultBlob {
  if (typeof value !== "object" || value === null) return false;
  const blob = value as Record<string, unknown>;
  if (typeof blob.iv !== "string" || typeof blob.ciphertext !== "string") return false;
  if (typeof blob.updated_at !== "string") return false;

  if (blob.v === 1) {
    const kdf = blob.kdf as VaultBlobV1["kdf"] | undefined;
    return (
      typeof kdf?.salt === "string" &&
      typeof kdf.iterations === "number" &&
      kdf.iterations >= 100_000 &&
      kdf.iterations <= 5_000_000
    );
  }
  if (blob.v === 2) {
    const wraps = blob.wraps as Partial<VaultBlobV2["wraps"]> | undefined;
    return (
      isWrappedKey(wraps?.password) &&
      (wraps.recovery === null || isWrappedKey(wraps.recovery))
    );
  }
  return false;
}
