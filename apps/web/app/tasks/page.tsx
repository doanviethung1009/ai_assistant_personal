import Link from "next/link";

import { ApiErrorPanel } from "@/components/api-error";
import { QuickAddForm } from "@/components/quick-add-form";
import { TaskItem } from "@/components/task-item";
import { listProjects, listTasks } from "@/lib/api";
import { OPEN_STATUSES, STATUS_LABELS, type Paged, type Project, type Task, type TaskStatus } from "@/lib/types";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 50;

interface SearchParams {
  q?: string;
  status?: string;
  closed?: string;
  page?: string;
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
  const includeClosed = params.closed === "1";
  const statuses = parseStatuses(params.status);
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  let result: Paged<Task>;
  let projects: Project[];

  try {
    [result, projects] = await Promise.all([
      listTasks({
        query: params.q,
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
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Tất cả task</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          {result.total} task khớp điều kiện
        </p>
      </div>

      <QuickAddForm projects={projects} />

      <form
        method="get"
        className="flex flex-col gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 sm:flex-row sm:items-end"
        aria-label="Lọc task"
      >
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

        <button
          type="submit"
          className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white"
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
  if (params.q) query.set("q", params.q);
  if (params.status) query.set("status", params.status);
  if (params.closed) query.set("closed", params.closed);
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
