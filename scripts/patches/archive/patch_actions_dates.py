import sys

file_path = "apps/web/app/actions.ts"
with open(file_path, "r") as f:
    c = f.read()

helper = """function parseJiraDate(val: any): string | null {
  if (!val || val === "No Due Date" || val === "Not Closed") return null;
  if (typeof val === "number") {
    const d = new Date(Math.round((val - 25569) * 86400 * 1000));
    return isNaN(d.getTime()) ? null : d.toISOString();
  }
  if (typeof val === "string") {
    // 2026-10-01T18:22:05.573+0700 -> 2026-10-01T18:22:05.573+07:00 (Next.js can parse this or we insert colon)
    const cleaned = val.replace(/([+-]\d{2})(\d{2})$/, "$1:$2");
    const d = new Date(cleaned);
    return isNaN(d.getTime()) ? null : d.toISOString();
  }
  return null;
}
"""

if "function parseJiraDate" not in c:
    c = c.replace("export async function syncFromUrlAction", helper + "\nexport async function syncFromUrlAction")

c = c.replace(
    "external_url: `https://onemount.atlassian.net/browse/${key}`,\n        assignee: ticket['Assignee'] ? String(ticket['Assignee']) : null",
    "external_url: `https://onemount.atlassian.net/browse/${key}`,\n        assignee: ticket['Assignee'] ? String(ticket['Assignee']) : null,\n        due_at: parseJiraDate(ticket['Due Date']),\n        created_at: parseJiraDate(ticket['Created Date']) || undefined"
)

with open(file_path, "w") as f:
    f.write(c)

print("Patched actions.ts for dates")
