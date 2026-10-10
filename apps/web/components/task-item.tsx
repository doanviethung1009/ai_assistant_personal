"use client";

import { useState, useTransition } from "react";
import {
  deleteTaskAction,
  logTimeAction,
  setScheduleAction,
  setScopeAction,
  setStatusAction,
} from "@/app/actions";
import { PriorityBadge, ProjectBadge, SourceBadge, StatusBadge, TagBadge } from "@/components/badges";
import { ScopeBadge } from "@/components/scope-badge";
import { isSyncManaged, scopeOf } from "@/lib/task-scope";
import {
  formatDue,
  formatMinutes,
  formatPlainDate,
  todayInDisplayTz,
} from "@/lib/format";
import { useDisplayTz } from "@/lib/timezone-context";
import { STATUS_LABELS, type Task, type TaskStatus } from "@/lib/types";

const ALL_STATUSES: TaskStatus[] = [
  "backlog",
  "todo",
  "in_progress",
  "blocked",
  "done",
  "cancelled",
];

const ICON_BUTTON =
  "rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1.5 text-xs font-medium text-[var(--color-ink-muted)] transition-all hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink)] hover:border-[var(--color-border-hover)] disabled:opacity-40 shadow-sm";

export function TaskItem({ task }: { task: Task }) {
  const tz = useDisplayTz();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const isClosed = task.status === "done" || task.status === "cancelled";
  const scope = scopeOf(task);
  // Task do tích hợp quản lý: sync sau sẽ ghi đè trạng thái, tiêu đề... (chỉ cảnh báo, không khoá).
  const syncManaged = isSyncManaged(task);

  /**
   * Đổi scope, có hộp xác nhận khi việc đó đổi quan hệ với đồng bộ. Task tay
   * (không external_id hoặc source=manual) đổi qua lại không ảnh hưởng gì tới sync nên không hỏi.
   */
  function toggleScope() {
    const next = scope === "work" ? "personal" : "work";
    let message: string | null = null;
    if (next === "personal" && syncManaged) {
      message = "Task này sẽ KHÔNG còn được Jira cập nhật. Đồng bộ sau sẽ bỏ qua nó.";
    } else if (next === "work" && task.external_id && task.source !== "manual") {
      message = "Lần đồng bộ sau sẽ ghi đè tiêu đề, trạng thái... bằng dữ liệu Jira.";
    }
    if (message !== null && !window.confirm(message)) return;
    run(() => setScopeAction(task.id, next));
  }

  function run(action: () => Promise<{ ok: boolean; error?: string }>) {
    setError(null);
    startTransition(async () => {
      const result = await action();
      if (!result.ok) setError(result.error ?? "Thao tác thất bại");
    });
  }

  return (
    <li
      className={`group relative overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 transition-all duration-300 hover:shadow-md hover:-translate-y-0.5 hover:border-blue-500/30 ${
        pending ? "opacity-60 scale-[0.99]" : ""
      } ${isClosed ? "bg-[var(--color-surface)] opacity-70" : ""}`}
    >
      <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-[var(--color-accent)] to-purple-500 opacity-0 transition-opacity group-hover:opacity-100"></div>
      
      <div className="flex flex-col sm:flex-row sm:items-start gap-4">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div className="pt-0.5 relative z-10">
            <input
              type="checkbox"
              checked={task.status === "done"}
              disabled={pending}
              onChange={(event) =>
                run(() =>
                  setStatusAction(task.id, event.target.checked ? "done" : "todo"),
                )
              }
              aria-label={
                task.status === "done"
                  ? `Mở lại: ${task.title}`
                  : `Đánh dấu xong: ${task.title}`
              }
              className="size-5 rounded border-gray-300 text-[var(--color-accent)] focus:ring-[var(--color-accent)] cursor-pointer transition-transform hover:scale-110 shadow-sm"
            />
          </div>

          <div className="min-w-0 flex-1 relative z-10">
            <p
              className={`text-base font-bold tracking-tight transition-colors ${
                isClosed
                  ? "text-[var(--color-ink-muted)] line-through decoration-gray-500/30"
                  : "text-[var(--color-ink)] group-hover:text-blue-600 dark:group-hover:text-blue-400"
              }`}
            >
              {task.title}
            </p>

            {task.description ? (
              <p className="mt-1.5 line-clamp-2 text-xs text-[var(--color-ink-muted)] leading-relaxed">
                {task.description}
              </p>
            ) : null}

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <ScopeBadge scope={scope} />
              <StatusBadge status={task.status} />
              <PriorityBadge priority={task.priority} />
              <SourceBadge source={task.source} />
              {task.project ? (
                <ProjectBadge
                  projectKey={task.project.key}
                  color={task.project.color}
                />
              ) : null}
              {task.external_id ? (
                <a
                  href={task.external_url || undefined}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-full bg-blue-500/10 px-2.5 py-0.5 text-[11px] font-bold tracking-wide text-blue-600 dark:text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors shadow-sm"
                  title="Mở trên hệ thống gốc"
                >
                  {task.external_id}
                </a>
              ) : null}
              {task.assignee ? (
                <span className="rounded-full bg-orange-500/10 px-2.5 py-0.5 text-[11px] font-bold tracking-wide text-orange-600 dark:text-orange-400 border border-orange-500/20 shadow-sm">
                  @{task.assignee}
                </span>
              ) : null}
              {task.tags.map((tag) => (
                <TagBadge key={tag} tag={tag} />
              ))}
            </div>

            <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[var(--color-ink-muted)]">
              {task.due_at ? (
                <div className="flex items-center gap-1.5">
                  <dt className="font-medium opacity-70">Hạn:</dt>
                  <dd
                    className={`font-semibold ${
                      task.is_overdue ? "text-red-500 bg-red-500/10 px-1.5 py-0.5 rounded-md" : ""
                    }`}
                  >
                    {formatDue(task, tz)}
                    {task.is_overdue ? " (quá hạn)" : ""}
                  </dd>
                </div>
              ) : null}

              {task.scheduled_for ? (
                <div className="flex items-center gap-1.5">
                  <dt className="font-medium opacity-70">Dự định:</dt>
                  <dd className="font-semibold text-[var(--color-ink)]">{formatPlainDate(task.scheduled_for, tz)}</dd>
                </div>
              ) : null}

              {task.estimate_minutes ? (
                <div className="flex items-center gap-1.5">
                  <dt className="font-medium opacity-70">Ước lượng:</dt>
                  <dd className="font-semibold">{formatMinutes(task.estimate_minutes)}</dd>
                </div>
              ) : null}

              {task.spent_minutes > 0 ? (
                <div className="flex items-center gap-1.5">
                  <dt className="font-medium opacity-70">Đã làm:</dt>
                  <dd className="font-semibold text-emerald-500">{formatMinutes(task.spent_minutes)}</dd>
                </div>
              ) : null}
            </dl>

            {error ? (
              <p role="alert" className="mt-3 text-xs font-medium text-red-500 bg-red-500/10 px-3 py-2 rounded-lg border border-red-500/20">
                {error}
              </p>
            ) : null}
          </div>
        </div>

        {/* Cụm Action */}
        <div className="flex sm:flex-col items-center sm:items-end justify-between sm:justify-start gap-3 mt-4 sm:mt-0 w-full sm:w-auto border-t sm:border-t-0 border-[var(--color-border)] pt-4 sm:pt-0 relative z-10">
          <div>
            <label htmlFor={`status-${task.id}`} className="sr-only">
              Trạng thái của {task.title}
            </label>
            <select
              id={`status-${task.id}`}
              value={task.status}
              disabled={pending}
              onChange={(event) =>
                run(() => setStatusAction(task.id, event.target.value as TaskStatus))
              }
              title={
                syncManaged
                  ? "Đồng bộ từ Jira: trạng thái sẽ bị ghi đè ở lần đồng bộ sau."
                  : undefined
              }
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-xs font-medium text-[var(--color-ink)] shadow-sm focus:ring-2 focus:ring-[var(--color-accent)] outline-none transition-shadow"
            >
              {ALL_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {STATUS_LABELS[status]}
                </option>
              ))}
            </select>
            {syncManaged ? (
              <p className="mt-1 max-w-[11rem] text-right text-[10px] leading-tight text-[var(--color-ink-muted)]">
                Đồng bộ từ Jira: trạng thái sẽ bị ghi đè ở lần đồng bộ sau.
              </p>
            ) : null}
          </div>

          <div className="flex gap-1.5">
            <button
              type="button"
              disabled={pending}
              onClick={toggleScope}
              className={ICON_BUTTON}
              title={
                scope === "work"
                  ? "Tách khỏi đồng bộ, coi là việc riêng"
                  : "Đưa về việc công ty"
              }
            >
              {scope === "work" ? "Chuyển thành cá nhân" : "Chuyển thành công việc"}
            </button>
            {!isClosed && task.scheduled_for !== todayInDisplayTz(tz) ? (
              <button
                type="button"
                disabled={pending}
                onClick={() =>
                  run(() => setScheduleAction(task.id, todayInDisplayTz(tz)))
                }
                className={ICON_BUTTON}
                title="Xếp vào hôm nay"
              >
                Hôm nay
              </button>
            ) : null}

            {!isClosed ? (
              <button
                type="button"
                disabled={pending}
                onClick={() => run(() => logTimeAction(task.id, 30))}
                className={ICON_BUTTON}
                title="Ghi thêm 30 phút đã làm"
              >
                +30p
              </button>
            ) : null}

            {!isClosed ? (
              <button
                type="button"
                disabled={pending}
                onClick={() => run(() => setStatusAction(task.id, "done"))}
                className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400 transition-all hover:bg-emerald-500 hover:text-white shadow-sm"
                title="Đánh dấu hoàn thành"
              >
                Xong
              </button>
            ) : null}

            {confirmingDelete ? (
              <>
                <button
                  type="button"
                  disabled={pending}
                  onClick={() => run(() => deleteTaskAction(task.id))}
                  className="rounded-lg border border-red-500 bg-red-500 px-2.5 py-1.5 text-xs font-bold text-white shadow-sm hover:bg-red-600 transition-colors"
                >
                  Xoá thật
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmingDelete(false)}
                  className={ICON_BUTTON}
                >
                  Huỷ
                </button>
              </>
            ) : (
              <button
                type="button"
                disabled={pending}
                onClick={() => setConfirmingDelete(true)}
                className="rounded-lg border border-transparent hover:border-red-500/30 bg-transparent hover:bg-red-500/10 px-2.5 py-1.5 text-xs font-medium text-[var(--color-ink-muted)] hover:text-red-500 transition-all opacity-0 md:group-hover:opacity-100 focus:opacity-100"
                title={`Xoá task ${task.title}`}
              >
                Xoá
              </button>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}
