import sys
file_path = "apps/web/app/team/page.tsx"
with open(file_path, "r") as f:
    c = f.read()

# Add pagination constants and vars
c = c.replace(
    'export const dynamic = "force-dynamic";',
    'export const dynamic = "force-dynamic";\n\nconst PAGE_SIZE = 50;'
)

c = c.replace(
    "searchParams: Promise<{ assignee?: string; status?: string; sort?: string }>;",
    "searchParams: Promise<{ assignee?: string; status?: string; sort?: string; page?: string }>;"
)

c = c.replace(
    'const currentSort = sp.sort || "all";',
    'const currentSort = sp.sort || "all";\n  const page = Math.max(1, Number.parseInt(sp.page ?? "1", 10) || 1);'
)

# Pagination logic
c = c.replace(
    "const makeLink = (updates: Record<string, string | undefined>) => {",
    """const totalPages = Math.max(1, Math.ceil(teamTasks.length / PAGE_SIZE));
    const paginatedTasks = teamTasks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

    const makeLink = (updates: Record<string, string | undefined>) => {"""
)

# Render paginated tasks and the pagination nav
c = c.replace(
    """        <div>
          <p className="text-sm text-[var(--color-ink-muted)] mb-3">Hiển thị {teamTasks.length} task</p>
          {teamTasks.length === 0 ? (
            <p className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-ink-muted)]">
              Không có task nào khớp với điều kiện lọc.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {teamTasks.map((task) => (
                <TaskItem key={task.id} task={task} />
              ))}
            </ul>
          )}
        </div>
      </div>
    );
  } catch (error) {""",
    """        <div>
          <p className="text-sm text-[var(--color-ink-muted)] mb-3">Tổng cộng {teamTasks.length} task (Trang {page}/{totalPages})</p>
          {paginatedTasks.length === 0 ? (
            <p className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-ink-muted)]">
              Không có task nào khớp với điều kiện lọc.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {paginatedTasks.map((task) => (
                <TaskItem key={task.id} task={task} />
              ))}
            </ul>
          )}
        </div>

        {totalPages > 1 && (
          <nav aria-label="Phân trang" className="flex items-center justify-between text-sm mt-4">
            <PageLink page={page - 1} sp={sp} disabled={page <= 1} label="Trang trước" />
            <span className="text-[var(--color-ink-muted)]">Trang {page} / {totalPages}</span>
            <PageLink page={page + 1} sp={sp} disabled={page >= totalPages} label="Trang sau" />
          </nav>
        )}
      </div>
    );
  } catch (error) {"""
)

# Append PageLink function
c = c + """\n
function PageLink({
  page,
  sp,
  disabled,
  label,
}: {
  page: number;
  sp: any;
  disabled: boolean;
  label: string;
}) {
  if (disabled) {
    return (
      <span className="cursor-not-allowed rounded-md border border-[var(--color-border)] px-3 py-1.5 text-[var(--color-ink-muted)] opacity-40">
        {label}
      </span>
    );
  }

  const query = new URLSearchParams();
  if (sp.assignee) query.set("assignee", sp.assignee);
  if (sp.status) query.set("status", sp.status);
  if (sp.sort) query.set("sort", sp.sort);
  query.set("page", String(page));

  return (
    <Link
      href={`/team?${query.toString()}`}
      className="rounded-md border border-[var(--color-border)] px-3 py-1.5 transition-colors hover:bg-[var(--color-surface-hover)]"
    >
      {label}
    </Link>
  );
}
"""

with open(file_path, "w") as f:
    f.write(c)

print("Added pagination to Team page")
