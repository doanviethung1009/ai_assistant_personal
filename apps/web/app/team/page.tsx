import { listTasks } from "@/lib/api";
import { JiraQuickSync } from "@/components/jira-quick-sync";
import { TaskItem } from "@/components/task-item";
import { ApiErrorPanel } from "@/components/api-error";
import Link from "next/link";
import { OPEN_STATUSES, type Task } from "@/lib/types";

export const dynamic = "force-dynamic";

/** Nhóm task công việc chưa có người nhận. */
const UNASSIGNED = "Chưa giao";

/** Backend giới hạn limit <= 200 mỗi trang. */
const FETCH_PAGE = 200;
/** Chặn vòng lặp vô hạn nếu total thay đổi giữa các lần gọi (tối đa 20 000 task). */
const MAX_FETCH_PAGES = 100;

/**
 * Tải toàn bộ task công việc (kể cả đã đóng) bằng nhiều trang 200.
 *
 * Vì sao còn tải hết: /team lọc theo ngày hoạt động và đếm theo assignee ngay
 * ở server component, mà backend chưa có endpoint cho hai việc đó. Chuyển sang
 * phân trang server-side thật cần epic riêng (spec task-scope S12). Trước đây
 * gọi limit=10000 nên chế độ api bị 422.
 */
async function listAllWorkTasks(): Promise<Task[]> {
  const all: Task[] = [];
  for (let i = 0; i < MAX_FETCH_PAGES; i++) {
    const res = await listTasks({
      view: "work",
      includeClosed: true,
      limit: FETCH_PAGE,
      offset: all.length,
      sortBy: "created_at",
      sortDesc: true,
    });
    all.push(...res.items);
    if (res.items.length === 0 || all.length >= res.total) break;
  }
  return all;
}
export default async function TeamPage({
  searchParams,
}: {
  searchParams: Promise<{ assignee?: string; status?: string; sort?: string; page?: string; q?: string; size?: string; time?: string; from?: string; to?: string }>;
}) {
  const sp = await searchParams;
  const currentAssignee = sp.assignee;
  const currentStatus = sp.status || "open"; // "open", "closed", "all"
  const currentSort = sp.sort || "all";
  const currentQ = sp.q || "";
  const currentTime = sp.time || "all";
  const currentFrom = sp.from || "";
  const currentTo = sp.to || "";
  const page = Math.max(1, Number.parseInt(sp.page ?? "1", 10) || 1); // "newest", "oldest"
  
  // Tối ưu pageSize: hỗ trợ chọn 50, 100, 200, 500
  const PAGE_SIZE = Math.max(10, Math.min(1000, Number.parseInt(sp.size ?? "50", 10) || 50));

  try {
    const allTasks = await listAllWorkTasks();

    // 1. Danh sách cơ bản: mọi task công việc (scope=work), kể cả task giao cho
    // chính mình để có cái nhìn tổng hợp. Task cá nhân không bao giờ hiện ở đây.
    let teamTasks = allTasks;
    
    // 2. Lọc theo status
    if (currentStatus === "open") {
      teamTasks = teamTasks.filter(t => OPEN_STATUSES.includes(t.status));
    } else if (currentStatus === "closed") {
      teamTasks = teamTasks.filter(t => !OPEN_STATUSES.includes(t.status));
    }

    // 3. Lọc theo từ khoá (title, tags)
    if (currentQ) {
      const needle = currentQ.trim().toLowerCase();
      teamTasks = teamTasks.filter(t => 
        t.title.toLowerCase().includes(needle) ||
        t.tags.some(tag => tag.toLowerCase().includes(needle))
      );
    }
    
    // Helper để lấy timestamp an toàn
    const getTaskDateMs = (t: typeof teamTasks[0]) => {
      // Nếu task đã hoàn thành/hủy, ưu tiên thời gian hoàn thành (completed_at)
      // Nếu đang mở, dùng updated_at hoặc created_at
      const dateStr = (!OPEN_STATUSES.includes(t.status) && t.completed_at) 
        ? t.completed_at 
        : (t.updated_at || t.created_at);
        
      if (!dateStr) return 0;
      const ms = new Date(dateStr).getTime();
      return Number.isNaN(ms) ? 0 : ms;
    };

    // 4. Theo mốc thời gian (cập nhật gần nhất - vì Jira sync quan trọng update)
    if (currentTime !== "all") {
      const now = new Date().getTime();
      let limit = 0;
      if (currentTime === "1d") limit = now - 1 * 24 * 60 * 60 * 1000;
      if (currentTime === "3d") limit = now - 3 * 24 * 60 * 60 * 1000;
      if (currentTime === "7d") limit = now - 7 * 24 * 60 * 60 * 1000;
      if (currentTime === "30d") limit = now - 30 * 24 * 60 * 60 * 1000;
      
      if (limit > 0) {
        teamTasks = teamTasks.filter(t => getTaskDateMs(t) >= limit);
      }
    }
    
    // 5. Theo khoảng thời gian tùy chọn (Date Range)
    if (currentFrom) {
      const fromMs = new Date(currentFrom).getTime();
      if (!Number.isNaN(fromMs)) {
        teamTasks = teamTasks.filter(t => getTaskDateMs(t) >= fromMs);
      }
    }
    if (currentTo) {
      const toMs = new Date(currentTo).getTime() + 24 * 60 * 60 * 1000 - 1; // Hết ngày đó
      if (!Number.isNaN(toMs)) {
        teamTasks = teamTasks.filter(t => getTaskDateMs(t) <= toMs);
      }
    }

    // --- Tính toán lại số lượng Task CỦA TỪNG NGƯỜI (Dựa trên bộ lọc đã áp dụng ở trên) ---
    const assigneeCounts: Record<string, number> = {};
    
    // Khởi tạo danh sách assignees đầy đủ từ allTasks với giá trị 0
    for (const t of allTasks) {
      assigneeCounts[t.assignee || UNASSIGNED] = 0;
    }

    // Đếm số lượng task thoả mãn bộ lọc
    for (const t of teamTasks) {
      const name = t.assignee || UNASSIGNED;
      assigneeCounts[name] = (assigneeCounts[name] || 0) + 1;
    }
    const assignees = Object.keys(assigneeCounts).sort();

    // 6. Cuối cùng, lọc theo Assignee để ra danh sách task hiển thị
    if (currentAssignee) {
      if (currentAssignee === UNASSIGNED) {
        teamTasks = teamTasks.filter(t => !t.assignee);
      } else {
        teamTasks = teamTasks.filter(t => t.assignee === currentAssignee);
      }
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
      if (currentTime !== "all") q.set("time", currentTime);
      if (currentFrom) q.set("from", currentFrom);
      if (currentTo) q.set("to", currentTo);
      
      for (const [k, v] of Object.entries(updates)) {
        if (v === undefined) q.delete(k);
        else q.set(k, v);
      }
      return `/team${q.toString() ? '?' + q.toString() : ''}`;
    };

    return (
      <div className="flex flex-col gap-8 pb-12 max-w-6xl mx-auto w-full">
        <div className="flex items-start justify-between relative">
          <div className="absolute -inset-1 bg-gradient-to-r from-orange-500 to-amber-500 rounded-lg blur opacity-10 pointer-events-none"></div>
          <div className="relative">
            <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-[var(--color-ink)] to-gray-400 bg-clip-text text-transparent flex items-center gap-3">
              <div className="p-2 bg-orange-500/10 rounded-xl">
                <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-orange-500"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M22 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
              </div>
              Giao việc / Team
            </h1>
            <p className="mt-2 text-sm text-[var(--color-ink-muted)] font-medium">
              Tổng hợp task công việc (Jira) của cả team. Task cá nhân không hiện ở đây.
            </p>
          </div>
          <div className="relative z-10">
            <JiraQuickSync />
          </div>
        </div>

        <div className="flex flex-col gap-5 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-6 shadow-sm">
          
          {/* Ô Tìm kiếm */}
          <form method="get" action="/team" className="flex gap-2">
            {currentAssignee && <input type="hidden" name="assignee" value={currentAssignee} />}
            {currentStatus !== "open" && <input type="hidden" name="status" value={currentStatus} />}
            {currentSort !== "newest" && <input type="hidden" name="sort" value={currentSort} />}
            {PAGE_SIZE !== 50 && <input type="hidden" name="size" value={PAGE_SIZE} />}
            {currentTime !== "all" && <input type="hidden" name="time" value={currentTime} />}
            {currentFrom && <input type="hidden" name="from" value={currentFrom} />}
            {currentTo && <input type="hidden" name="to" value={currentTo} />}
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

          {/* Lọc Mốc thời gian nhanh & Custom Range */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium w-24">Cập nhật lúc:</span>
            {[
              { id: "all", label: "Tất cả" },
              { id: "1d", label: "1 ngày qua" },
              { id: "3d", label: "3 ngày qua" },
              { id: "7d", label: "7 ngày qua" },
              { id: "30d", label: "30 ngày qua" }
            ].map(tr => (
              <Link
                key={tr.id}
                href={makeLink({ time: tr.id === "all" ? undefined : tr.id, from: undefined, to: undefined })}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  currentTime === tr.id && !currentFrom && !currentTo
                    ? "bg-[var(--color-accent)] text-white"
                    : "border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)]"
                }`}
              >
                {tr.label}
              </Link>
            ))}

            <form method="get" action="/team" className="flex items-center gap-2 ml-2 pl-2 border-l border-[var(--color-border)]">
              {currentAssignee && <input type="hidden" name="assignee" value={currentAssignee} />}
              {currentStatus !== "open" && <input type="hidden" name="status" value={currentStatus} />}
              {currentSort !== "newest" && <input type="hidden" name="sort" value={currentSort} />}
              {currentQ && <input type="hidden" name="q" value={currentQ} />}
              {PAGE_SIZE !== 50 && <input type="hidden" name="size" value={PAGE_SIZE} />}
              {/* Reset time preset when using custom range */}
              <input type="hidden" name="time" value="all" />
              
              <input type="date" name="from" defaultValue={currentFrom} className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-0.5 text-xs text-[var(--color-ink)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]" title="Từ ngày" />
              <span className="text-[var(--color-ink-muted)] text-xs">-</span>
              <input type="date" name="to" defaultValue={currentTo} className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-0.5 text-xs text-[var(--color-ink)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]" title="Đến ngày" />
              <button type="submit" className="rounded-md bg-[var(--color-surface-hover)] border border-[var(--color-border)] px-2 py-0.5 text-xs font-medium hover:bg-[var(--color-accent)] hover:text-white transition-colors">Lọc</button>
            </form>
          </div>

          {/* Hiển thị trên mỗi trang */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium w-24">Hiển thị:</span>
            {[
              { id: "50", label: "50 / trang" },
              { id: "100", label: "100 / trang" },
              { id: "200", label: "200 / trang" },
              { id: "500", label: "500 / trang" }
            ].map(sz => (
              <Link
                key={sz.id}
                href={makeLink({ size: sz.id })}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  PAGE_SIZE === Number(sz.id)
                    ? "bg-[var(--color-accent)] text-white"
                    : "border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)]"
                }`}
              >
                {sz.label}
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
  if (sp.size) query.set("size", sp.size);
  if (sp.time) query.set("time", sp.time);
  if (sp.from) query.set("from", sp.from);
  if (sp.to) query.set("to", sp.to);
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
