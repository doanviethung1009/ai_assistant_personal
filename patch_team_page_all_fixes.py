import sys
file_path = "apps/web/app/team/page.tsx"
with open(file_path, "r") as f:
    c = f.read()

# Fix listTasks options to include closed tasks
c = c.replace(
    "await listTasks({ limit: 5000 });",
    "await listTasks({ limit: 5000, includeClosed: true });"
)

# Extract assignees and their counts
c = c.replace(
    "const assignees = Array.from(new Set(allTasks.map(t => t.assignee).filter(Boolean))) as string[];\n    assignees.sort();",
    """// Tính tổng số task cho từng người (ngoại trừ "Đoàn Việt Hưng")
    const assigneeCounts: Record<string, number> = {};
    for (const t of allTasks) {
      if (t.assignee && t.assignee !== "Đoàn Việt Hưng") {
        assigneeCounts[t.assignee] = (assigneeCounts[t.assignee] || 0) + 1;
      }
    }
    const assignees = Object.keys(assigneeCounts).sort();"""
)

# Update Link labels to include counts
c = c.replace(
    """<Link
                    key={name}
                    href={makeLink({ assignee: name })}
                    className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                      currentAssignee === name
                        ? "bg-[var(--color-accent)] text-white"
                        : "border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)]"
                    }`}
                  >
                    {name}
                  </Link>""",
    """<Link
                    key={name}
                    href={makeLink({ assignee: name })}
                    className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                      currentAssignee === name
                        ? "bg-[var(--color-accent)] text-white"
                        : "border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)]"
                    }`}
                  >
                    {name} ({assigneeCounts[name]})
                  </Link>"""
)

with open(file_path, "w") as f:
    f.write(c)
print("Patched Team page for includeClosed and counts")
