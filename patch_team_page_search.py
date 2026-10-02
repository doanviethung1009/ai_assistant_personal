import sys

file_path = "apps/web/app/team/page.tsx"
with open(file_path, "r") as f:
    c = f.read()

# 1. Update searchParams
c = c.replace(
    "searchParams: Promise<{ assignee?: string; status?: string; sort?: string; page?: string }>;",
    "searchParams: Promise<{ assignee?: string; status?: string; sort?: string; page?: string; q?: string }>;"
)

c = c.replace(
    "const currentSort = sp.sort || \"all\";",
    "const currentSort = sp.sort || \"all\";\n  const currentQ = sp.q || \"\";"
)

# 2. Add filter logic for query
filter_logic = """    // 2. Theo status
    if (currentStatus === "open") {
      teamTasks = teamTasks.filter(t => OPEN_STATUSES.includes(t.status));
    } else if (currentStatus === "closed") {
      teamTasks = teamTasks.filter(t => !OPEN_STATUSES.includes(t.status));
    }

    // 2.5 Theo từ khoá (title, tags)
    if (currentQ) {
      const needle = currentQ.trim().toLowerCase();
      teamTasks = teamTasks.filter(t => 
        t.title.toLowerCase().includes(needle) ||
        t.tags.some(tag => tag.toLowerCase().includes(needle))
      );
    }"""
c = c.replace(
    """    // 2. Theo status
    if (currentStatus === "open") {
      teamTasks = teamTasks.filter(t => OPEN_STATUSES.includes(t.status));
    } else if (currentStatus === "closed") {
      teamTasks = teamTasks.filter(t => !OPEN_STATUSES.includes(t.status));
    }""",
    filter_logic
)

# 3. Update makeLink and PageLink to preserve q
c = c.replace(
    "if (currentSort !== \"newest\") q.set(\"sort\", currentSort);",
    "if (currentSort !== \"newest\") q.set(\"sort\", currentSort);\n      if (currentQ) q.set(\"q\", currentQ);"
)
c = c.replace(
    "if (sp.sort) query.set(\"sort\", sp.sort);",
    "if (sp.sort) query.set(\"sort\", sp.sort);\n  if (sp.q) query.set(\"q\", sp.q);"
)

# 4. Add the Search Bar HTML
search_html = """        <div className="flex flex-col gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4">
          
          {/* Ô Tìm kiếm */}
          <form method="get" className="flex gap-2">
            {currentAssignee && <input type="hidden" name="assignee" value={currentAssignee} />}
            {currentStatus !== "open" && <input type="hidden" name="status" value={currentStatus} />}
            {currentSort !== "newest" && <input type="hidden" name="sort" value={currentSort} />}
            <input
              type="search"
              name="q"
              defaultValue={currentQ}
              placeholder="Tìm theo tiêu đề, project hoặc tag..."
              className="flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm"
            />
            <button type="submit" className="rounded-md bg-[var(--color-accent)] px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-[var(--color-accent-hover)]">
              Tìm
            </button>
          </form>

          {/* Lọc Trạng thái */}"""
c = c.replace(
    """        <div className="flex flex-col gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4">
          
          {/* Lọc Trạng thái */}""",
    search_html
)

with open(file_path, "w") as f:
    f.write(c)
print("Added Search Bar to Team page")
