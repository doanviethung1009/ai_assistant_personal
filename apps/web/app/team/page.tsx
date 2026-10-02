import { listTasks } from "@/lib/api";
import { TaskItem } from "@/components/task-item";
import { ApiErrorPanel } from "@/components/api-error";
import Link from "next/link";
import { OPEN_STATUSES, TaskStatus } from "@/lib/types";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 50;

export default async function TeamPage({
  searchParams,
}: {
  searchParams: Promise<{ assignee?: string; status?: string; sort?: string; page?: string; q?: string }>;
}) {
  const sp = await searchParams;
  const currentAssignee = sp.assignee;
  const currentStatus = sp.status || "open"; // "open", "closed", "all"
  const currentSort = sp.sort || "all";
  const currentQ = sp.q || "";
  const page = Math.max(1, Number.parseInt(sp.page ?? "1", 10) || 1); // "newest", "oldest"

  try {
    // limit cao để demo, thực tế nên có pagination
    const { items: allTasks } = await listTasks({ limit: 5000, includeClosed: true });
    
    // Lọc ra các assignee duy nhất (bỏ null)
    // Tính tổng số task cho từng người (ngoại trừ "Đoàn Việt Hưng")
    const assigneeCounts: Record<string, number> = {};
    for (const t of allTasks) {
      if (t.assignee && t.assignee !== "Đoàn Việt Hưng") {
        assigneeCounts[t.assignee] = (assigneeCounts[t.assignee] || 0) + 1;
      }
    }
    const assignees = Object.keys(assigneeCounts).sort();

    // Lọc task theo điều kiện
    let teamTasks = allTasks.filter(t => t.assignee && t.assignee !== "Đoàn Việt Hưng");
    
    // 1. Theo assignee
    if (currentAssignee) {
      teamTasks = teamTasks.filter(t => t.assignee === currentAssignee);
    }
    
    // 2. Theo status
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
    }
    
    // 3. Theo thời gian (sort)
    if (currentSort !== "all") {
      teamTasks.sort((a, b) => {
        const dateA = new Date(a.created_at).getTime();
        const dateB = new Date(b.created_at).getTime();
        return currentSort === "newest" ? dateB - dateA : dateA - dateB;
      });
    }

    // Helper tạo link filter
    const totalPages = Math.max(1, Math.ceil(teamTasks.length / PAGE_SIZE));
    const paginatedTasks = teamTasks.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

    const makeLink = (updates: Record<string, string | undefined>) => {
      const q = new URLSearchParams();
      if (currentAssignee) q.set("assignee", currentAssignee);
      if (currentStatus !== "open") q.set("status", currentStatus);
      if (currentSort !== "newest") q.set("sort", currentSort);
      if (currentQ) q.set("q", currentQ);
      
      for (const [k, v] of Object.entries(updates)) {
        if (v === undefined) q.delete(k);
        else q.set(k, v);
      }
      return `/team${q.toString() ? '?' + q.toString() : ''}`;
    };

    return (
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Giao việc / Team</h1>
          <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
            Tổng hợp tất cả các task được giao cho người khác trong hệ thống.
          </p>
        </div>

        <div className="flex flex-col gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4">
          
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

          {/* Lọc Trạng thái */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium w-24">Trạng thái:</span>
            {[
              { id: "all", label: "Tất cả" },
              { id: "open", label: "Đang mở" },
              { id: "closed", label: "Đã hoàn thành" }
            ].map(st => (
              <Link
                key={st.id}
                href={makeLink({ status: st.id === "open" ? undefined : st.id })}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  currentStatus === st.id
                    ? "bg-[var(--color-accent)] text-white"
                    : "border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)]"
                }`}
              >
                {st.label}
              </Link>
            ))}
          </div>
          
          {/* Sắp xếp Thời gian */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium w-24">Thời gian tạo:</span>
            {[
              { id: "all", label: "Tất cả" },
              { id: "newest", label: "Mới nhất" },
              { id: "oldest", label: "Cũ nhất" }
            ].map(so => (
              <Link
                key={so.id}
                href={makeLink({ sort: so.id === "all" ? undefined : so.id })}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  currentSort === so.id
                    ? "bg-[var(--color-accent)] text-white"
                    : "border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)]"
                }`}
              >
                {so.label}
              </Link>
            ))}
          </div>

          {/* Lọc Người */}
          {assignees.length > 0 && (
            <div className="flex items-start gap-2">
              <span className="text-sm font-medium w-24 pt-1">Người làm:</span>
              <div className="flex flex-wrap gap-2 flex-1">
                <Link
                  href={makeLink({ assignee: undefined })}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                    !currentAssignee
                      ? "bg-[var(--color-accent)] text-white"
                      : "border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)]"
                  }`}
                >
                  Tất cả
                </Link>
                {assignees.map((name) => (
                  <Link
                    key={name}
                    href={makeLink({ assignee: name })}
                    className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                      currentAssignee === name
                        ? "bg-[var(--color-accent)] text-white"
                        : "border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)]"
                    }`}
                  >
                    {name} ({assigneeCounts[name]})
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>

        <div>
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
  } catch (error) {
    return (
      <ApiErrorPanel
        message={error instanceof Error ? error.message : String(error)}
      />
    );
  }
}


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
  if (sp.q) query.set("q", sp.q);
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
