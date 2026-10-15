/**
 * Làm sạch chuỗi từ nguồn ngoài (Jira, Excel, form) và chặn CSV/Excel formula injection.
 * Không "server-only": test và client đều dùng được. Phải cùng hành vi với `clean_text` /
 * `clean_person_name` ở apps/core/app/services/jira_mapping.py (sửa bên này thì sửa bên kia).
 */

/** ZWJ/ZWNJ được giữ trong clean_text (emoji, chữ Ấn/Ba Tư) như bản Python. */
const KEEP_CF = new Set(["‌", "‍"]);
const MAX_JQL_LEN = 4000;
export const MAX_REPORTER_LEN = 200;

/** Bỏ Cc/Cf (trừ ZWJ/ZWNJ); \n \r \t và Zl/Zp thành khoảng trắng; strip. */
export function cleanText(value: unknown): string {
  if (typeof value !== "string") return "";
  let out = "";
  for (const ch of value) {
    if (ch === "\u2028" || ch === "\u2029" || ch === "\n" || ch === "\r" || ch === "\t") out += " ";
    else if (/^\p{Cc}$/u.test(ch) || (/^\p{Cf}$/u.test(ch) && !KEEP_CF.has(ch))) continue;
    else out += ch;
  }
  return out.trim();
}

/**
 * Tên người (assignee/reporter/alias) sạch; rỗng nếu chỉ còn khoảng trắng hoặc ký tự vô hình
 * (NBSP, zero-width space, ZWJ/ZWNJ toàn bộ). Rỗng thì người gọi phải BỎ mục đó.
 */
export function cleanName(value: unknown): string {
  const text = cleanText(value);
  for (const ch of text) {
    if (!/\s/u.test(ch) && !KEEP_CF.has(ch)) return text;
  }
  return "";
}

/** displayName của reporter: làm sạch, cắt MAX_REPORTER_LEN, rỗng thì null (như jira_mapping.py). */
export function cleanReporter(value: unknown): string | null {
  const name = cleanName(value);
  if (!name) return null;
  return name.length > MAX_REPORTER_LEN ? name.slice(0, MAX_REPORTER_LEN).trim() || null : name;
}

/**
 * Vô hiệu hoá ô CSV bị Excel/Sheets hiểu là công thức: bắt đầu bằng = + - @ tab hoặc CR thì thêm
 * tiền tố dấu nháy đơn. `parseCsv` gỡ đúng tiền tố này khi nhập lại để export rồi import không đổi dữ liệu.
 */
export function neutralizeCsvCell(value: string): string {
  return /^[=+\-@\t\r]/.test(value) ? `'${value}` : value;
}

/** Ngược của neutralizeCsvCell, chỉ gỡ khi sau dấu nháy là ký tự kích hoạt công thức. */
export function restoreCsvCell(value: string): string {
  return /^'[=+\-@\t\r]/.test(value) ? value.slice(1) : value;
}

/** Từ chối JQL dài hơn 4000 ký tự (cùng trần và thông báo với `build_jql` bản Python). */
export function checkJqlLength(jql: string): string | null {
  return jql.length > MAX_JQL_LEN ? "JQL quá dài" : null;
}
