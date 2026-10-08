/**
 * Issue key hợp lệ của Jira. Cùng regex với core (`_ISSUE_KEY_RE` ở
 * apps/core/app/services/jira_mapping.py, dùng fullmatch); `^...$` ở đây không nhận "\n" cuối
 * vì JS `$` không có cờ m chỉ khớp cuối chuỗi. Sửa bên này thì sửa bên kia.
 */
const ISSUE_KEY_RE = /^[A-Z][A-Z0-9_]{1,254}-[0-9]{1,9}$/;

export function isValidIssueKey(key: unknown): key is string {
  return typeof key === "string" && ISSUE_KEY_RE.test(key);
}

/** Bọc chuỗi trong JQL "..." và escape \ và " để giá trị người dùng không thoát khỏi chuỗi. */
export function jqlQuote(value: string): string {
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}
