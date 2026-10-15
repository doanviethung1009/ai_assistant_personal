/**
 * Chuẩn hoá và kiểm tra danh sách alias Jira nhập tay (form tạo/mời user, alias-editor).
 * Không "server-only": client dùng để báo lỗi sớm, Server Action dùng lại để KIỂM TRA THẬT
 * (client không đáng tin). Core vẫn là bên quyết định cuối.
 */

import { cleanName } from "./text-safety";

export const MAX_ALIASES = 20;
export const MAX_ALIAS_LENGTH = 200;
const CONTROL_RE = /[\x00-\x1f\x7f]/;

export type AliasesParse = { ok: true; aliases: string[] } | { ok: false; error: string };

/** Tách chuỗi nhập (dấu phẩy hoặc xuống dòng) thành các mục thô, chưa kiểm tra. */
export function splitAliasText(text: string): string[] {
  return text.split(/[,\n]/);
}

/**
 * Cắt khoảng trắng, bỏ mục rỗng, bỏ trùng (giữ thứ tự xuất hiện đầu), từ chối ký tự điều khiển,
 * mục > 200 ký tự và danh sách > 20 mục. Trùng KHÔNG phải lỗi: gộp im lặng như setAliasesAction.
 */
export function normalizeAliases(raw: unknown): AliasesParse {
  if (!Array.isArray(raw)) return { ok: false, error: "Danh sách alias không hợp lệ." };
  const seen = new Set<string>();
  const aliases: string[] = [];
  for (const item of raw) {
    if (typeof item !== "string") return { ok: false, error: "Danh sách alias không hợp lệ." };
    // Tên chỉ toàn khoảng trắng/ký tự vô hình (NBSP, zero-width) coi là rỗng và bị bỏ; ký tự điều khiển
    // thì báo lỗi (kiểm trên chuỗi thô vì cleanName sẽ lặng lẽ xoá chúng).
    if (!cleanName(item) && !CONTROL_RE.test(item.trim())) continue;
    const alias = item.trim();
    if (alias.length > MAX_ALIAS_LENGTH || CONTROL_RE.test(alias)) {
      return { ok: false, error: `Alias tối đa ${MAX_ALIAS_LENGTH} ký tự, không chứa ký tự điều khiển.` };
    }
    if (seen.has(alias)) continue;
    seen.add(alias);
    aliases.push(alias);
  }
  if (aliases.length > MAX_ALIASES) return { ok: false, error: `Tối đa ${MAX_ALIASES} alias.` };
  return { ok: true, aliases };
}

/**
 * Làm sạch `aliases_skipped` từ core trước khi hiện: chỉ giữ chuỗi, cắt độ dài, giới hạn số lượng.
 * Thiếu field (core cũ) hoặc sai kiểu thì coi như không có mục nào bị bỏ qua.
 */
export function cleanSkippedAliases(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((x): x is string => typeof x === "string" && x.trim().length > 0)
    .map((x) => x.slice(0, MAX_ALIAS_LENGTH))
    .slice(0, MAX_ALIASES);
}

/** Câu cảnh báo khi một số alias không được gán. User VẪN đã được tạo. */
export function skippedAliasesMessage(skipped: string[], verb: "được tạo" | "được mời" = "được tạo"): string {
  const names = skipped.map((s) => `"${s}"`).join(", ");
  return `Người dùng đã ${verb}, nhưng các tên Jira ${names} không được gán vì đang thuộc người khác. Vào cột Alias Jira của người dùng để xử lý.`;
}
