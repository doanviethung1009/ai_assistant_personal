import Link from "next/link";
import { JiraQuickSync } from "@/components/jira-quick-sync";

import { ApiErrorPanel } from "@/components/api-error";
import { QuickAddForm } from "@/components/quick-add-form";
import { TaskItem } from "@/components/task-item";
import { listProjects, listTasks } from "@/lib/api";
import { TASK_VIEWS, parseView } from "@/lib/task-scope";
import {
  OPEN_STATUSES,
  STATUS_LABELS,
  VIEW_LABELS,
  type Paged,
  type Project,
  type Task,
  type TaskStatus,
  type TaskView,
} from "@/lib/types";

export const dynamic = "force-dynamic";

interface SearchParams {
  view?: string;
  q?: string;
  status?: string;
  closed?: string;
  page?: string;
  size?: string;
}

function parseStatuses(raw: string | undefined): TaskStatus[] | undefined {
  if (!raw) return undefined;
  const allowed = new Set<string>([...OPEN_STATUSES, "done", "cancelled"]);
  const values = raw
    .split(",")
    .map((value) => value.trim())
    .filter((value) => allowed.has(value)) as TaskStatus[];
  return values.length > 0 ? values : undefined;
}

export default async function TasksPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  // Giá trị lạ về `mine`. Tên "của tôi" (owner) KHÔNG đọc từ URL: api.ts lấy từ cài đặt server.
  const view = parseView(params.view);
  const includeClosed = params.closed === "1";
  const statuses = parseStatuses(params.status);
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);
  const PAGE_SIZE = Math.max(10, Math.min(1000, Number.parseInt(params.size ?? "50", 10) || 50));

  let result: Paged<Task>;
  let projects: Project[];

  try {
    [result, projects] = await Promise.all([
      listTasks({
        query: params.q,
        view,
        status: statuses,
        includeClosed,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
        sortBy: "created_at",
        sortDesc: true,
      }),
      listProjects(),
    ]);
  } catch (error) {
    return (
      <ApiErrorPanel
        message={error instanceof Error ? error.message : String(error)}
      />
    );
  }

  const totalPages = Math.max(1, Math.ceil(result.total / PAGE_SIZE));

  return (
    <div className="flex flex-col gap-8 pb-12 max-w-6xl mx-auto w-full">
      <div className="flex items-start justify-between relative">
        <div className="absolute -inset-1 bg-gradient-to-r from-blue-500 to-indigo-500 rounded-lg blur opacity-10 pointer-events-none"></div>
        <div className="relative">
          <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-[var(--color-ink)] to-gray-400 bg-clip-text text-transparent flex items-center gap-3">
            <div className="p-2 bg-indigo-500/10 rounded-xl">
              <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-indigo-500"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
            </div>
            Task
          </h1>
          <p className="mt-2 text-sm text-[var(--color-ink-muted)] font-medium">
            {result.total} task trong mục &ldquo;{VIEW_LABELS[view]}&rdquo;.
          </p>
        </div>
        <div className="relative z-10">
          <JiraQuickSync />
        </div>
      </div>

      <div className="relative rounded-2xl bg-gradient-to-br from-[var(--color-surface-raised)] to-[var(--color-surface)] p-2 shadow-sm border border-[var(--color-border)]">
        <QuickAddForm
          key={view}
          projects={projects}
          defaultScope={view === "work" ? "work" : "personal"}
        />
      </div>

      <nav aria-label="Loại task" className="flex flex-wrap gap-2">
        {TASK_VIEWS.map((value) => (
          <Link
            key={value}
            href={viewHref(value, params)}
            aria-current={view === value ? "page" : undefined}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
              view === value
                ? "bg-[var(--color-accent)] text-white"
                : "border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)]"
            }`}
          >
            {VIEW_LABELS[value]}
          </Link>
        ))}
      </nav>

      <form
        method="get"
        className="flex flex-col gap-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-6 shadow-sm sm:flex-row sm:items-end"
        aria-label="Lọc task"
      >
        {/* Giữ view khi lọc: form GET sẽ gửi lại đúng tab đang xem */}
        <input type="hidden" name="view" value={view} />
        <div className="flex-1">
          <label
            htmlFor="filter-q"
            className="mb-1 block text-xs font-medium text-[var(--color-ink-muted)]"
          >
            Tìm trong tiêu đề và mô tả
          </label>
          <input
            id="filter-q"
            name="q"
            type="search"
            defaultValue={params.q ?? ""}
            className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm"
            placeholder="deploy, review, homelab…"
          />
        </div>

        <div>
          <label
            htmlFor="filter-status"
            className="mb-1 block text-xs font-medium text-[var(--color-ink-muted)]"
          >
            Trạng thái
          </label>
          <select
            id="filter-status"
            name="status"
            defaultValue={params.status ?? ""}
            className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm"
          >
            <option value="">Tất cả đang mở</option>
            {(
              ["backlog", "todo", "in_progress", "blocked", "done", "cancelled"] as TaskStatus[]
            ).map((status) => (
              <option key={status} value={status}>
                {STATUS_LABELS[status]}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2 pb-2">
          <input
            id="filter-closed"
            name="closed"
            type="checkbox"
            value="1"
            defaultChecked={includeClosed}
            className="size-4 accent-[var(--color-accent)]"
          />
          <label htmlFor="filter-closed" className="text-sm">
            Gồm việc đã đóng
          </label>
        </div>

        <div>
          <label htmlFor="filter-size" className="mb-1 block text-xs font-medium text-[var(--color-ink-muted)]">
            Hiển thị
          </label>
          <select
            id="filter-size"
            name="size"
            defaultValue={PAGE_SIZE.toString()}
            className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm"
          >
            <option value="20">20 / trang</option>
            <option value="50">50 / trang</option>
            <option value="100">100 / trang</option>
            <option value="200">200 / trang</option>
            <option value="500">500 / trang</option>
          </select>
        </div>

        <button
          type="submit"
          className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white mb-[1px]"
        >
          Lọc
        </button>
      </form>

      {result.items.length === 0 ? (
        <p className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-ink-muted)]">
          Không có task nào khớp. Thử bỏ filter hoặc thêm task mới ở trên.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {result.items.map((task) => (
            <TaskItem key={task.id} task={task} />
          ))}
        </ul>
      )}

      {totalPages > 1 ? (
        <nav
          aria-label="Phân trang"
          className="flex items-center justify-between text-sm"
        >
          <PageLink
            page={page - 1}
            params={params}
            disabled={page <= 1}
            label="Trang trước"
          />
          <span className="text-[var(--color-ink-muted)]">
            Trang {page} / {totalPages}
          </span>
          <PageLink
            page={page + 1}
            params={params}
            disabled={page >= totalPages}
            label="Trang sau"
          />
        </nav>
      ) : null}
    </div>
  );
}

/** Link đổi tab: giữ bộ lọc nhưng về trang 1, vì số trang của tab cũ không còn nghĩa. */
function viewHref(view: TaskView, params: SearchParams): string {
  const query = new URLSearchParams();
  query.set("view", view);
  if (params.q) query.set("q", params.q);
  if (params.status) query.set("status", params.status);
  if (params.closed) query.set("closed", params.closed);
  if (params.size) query.set("size", params.size);
  return `/tasks?${query.toString()}`;
}

function PageLink({
  page,
  params,
  disabled,
  label,
}: {
  page: number;
  params: SearchParams;
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
  if (params.view) query.set("view", parseView(params.view));
  if (params.q) query.set("q", params.q);
  if (params.status) query.set("status", params.status);
  if (params.closed) query.set("closed", params.closed);
  if (params.size) query.set("size", params.size);
  query.set("page", String(page));

  return (
    <Link
      href={`/tasks?${query.toString()}`}
      className="rounded-md border border-[var(--color-border)] px-3 py-1.5 transition-colors hover:bg-[var(--color-surface-hover)]"
    >
      {label}
    </Link>
  );
}
