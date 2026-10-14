import { jqlQuote } from "./jira-issue-key";

export type PeopleRole = "both" | "assignee" | "reporter";

/**
 * Vai trò của ô "Theo người". Vắng/undefined coi là "assignee" (giữ hành vi cho client cũ);
 * giá trị lạ trả null để Server Action từ chối thay vì đoán.
 */
export function parsePeopleRole(raw: unknown): PeopleRole | null {
  if (raw === undefined || raw === null || raw === "") return "assignee";
  return raw === "both" || raw === "assignee" || raw === "reporter" ? raw : null;
}

/** Tách danh sách tên theo vai trò: "both" dùng cùng danh sách cho cả hai điều kiện. */
export function splitByRole(
  picked: string[],
  role: PeopleRole,
): { assignees: string[]; reporters: string[] } {
  return {
    assignees: role === "reporter" ? [] : picked,
    reporters: role === "assignee" ? [] : picked,
  };
}

/**
 * Ghép điều kiện người vào JQL gốc. PHẢI cho cùng chuỗi với `jira_client.build_jql` ở backend
 * (bảng 3.2 của docs/specs/jira-reporter.md).
 *
 * WHY bọc ngoặc khi có cả hai: AND ưu tiên hơn OR trong JQL. Thiếu ngoặc thì
 * `project in ("DBA") AND assignee in ("X") OR reporter in ("X")` kéo reporter X trên MỌI project,
 * tức vượt phạm vi kết nối. Mọi tên đi qua `jqlQuote`.
 *
 * `baseJql` là JQL kết nối đã bỏ ORDER BY (rỗng nếu không có JQL tuỳ chỉnh).
 */
export function buildPeopleJql(baseJql: string, assignees: string[], reporters: string[]): string {
  const conds: string[] = [];
  if (assignees.length > 0) conds.push(`assignee in (${assignees.map((n) => jqlQuote(n)).join(", ")})`);
  if (reporters.length > 0) conds.push(`reporter in (${reporters.map((n) => jqlQuote(n)).join(", ")})`);
  const cond = conds.length > 1 ? `(${conds.join(" OR ")})` : (conds[0] ?? "");
  return `${baseJql ? `(${baseJql}) AND ` : ""}${cond} ORDER BY updated DESC`;
}
