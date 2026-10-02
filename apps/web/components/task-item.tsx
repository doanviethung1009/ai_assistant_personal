"use client";

import { useState, useTransition } from "react";

import {
  deleteTaskAction,
  logTimeAction,
  setScheduleAction,
  setStatusAction,
} from "@/app/actions";
import { PriorityBadge, ProjectBadge, SourceBadge, StatusBadge, TagBadge } from "@/components/badges";
import {
  formatDateTime,
  formatMinutes,
  formatPlainDate,
  todayInDisplayTz,
} from "@/lib/format";
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
  "rounded-md border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-ink-muted)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink)] disabled:opacity-40";

export function TaskItem({ task }: { task: Task }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const isClosed = task.status === "done" || task.status === "cancelled";

  function run(action: () => Promise<{ ok: boolean; error?: string }>) {
    setError(null);
    startTransition(async () => {
      const result = await action();
      if (!result.ok) setError(result.error ?? "Thao tác thất bại");
    });
  }

  return (
    <li
      className={`rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3 transition-opacity ${
        pending ? "opacity-60" : ""
      }`}
    >
      <div className="flex items-start gap-3">
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
          className="mt-1 size-4 shrink-0 accent-[var(--color-accent)]"
        />

        <div className="min-w-0 flex-1">
          <p
            className={`text-sm font-medium ${
              isClosed
                ? "text-[var(--color-ink-muted)] line-through"
                : "text-[var(--color-ink)]"
            }`}
          >
            {task.title}
          </p>

          {task.description ? (
            <p className="mt-1 line-clamp-2 text-xs text-[var(--color-ink-muted)]">
              {task.description}
            </p>
          ) : null}

          <div className="mt-2 flex flex-wrap items-center gap-1.5">
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
                className="rounded-full bg-blue-500/15 px-2 py-0.5 text-xs font-medium text-blue-300 ring-1 ring-inset ring-blue-500/30 hover:bg-blue-500/25 transition-colors"
                title="Mở trên hệ thống gốc"
              >
                {task.external_id}
              </a>
            ) : null}
            {task.tags.map((tag) => (
              <TagBadge key={tag} tag={tag} />
            ))}
          </div>

          <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--color-ink-muted)]">
            {task.due_at ? (
              <div className="flex gap-1">
                <dt>Hạn:</dt>
                <dd
                  className={
                    task.is_overdue ? "font-medium text-[var(--color-danger)]" : ""
                  }
                >
                  {formatDateTime(task.due_at)}
                  {task.is_overdue ? " (quá hạn)" : ""}
                </dd>
              </div>
            ) : null}

            {task.scheduled_for ? (
              <div className="flex gap-1">
                <dt>Dự định:</dt>
                <dd>{formatPlainDate(task.scheduled_for)}</dd>
              </div>
            ) : null}

            {task.estimate_minutes ? (
              <div className="flex gap-1">
                <dt>Ước lượng:</dt>
                <dd>{formatMinutes(task.estimate_minutes)}</dd>
              </div>
            ) : null}

            {task.spent_minutes > 0 ? (
              <div className="flex gap-1">
                <dt>Đã làm:</dt>
                <dd>{formatMinutes(task.spent_minutes)}</dd>
              </div>
            ) : null}
          </dl>

          {error ? (
            <p role="alert" className="mt-2 text-xs text-[var(--color-danger)]">
              {error}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 flex-col items-end gap-2">
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
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-xs text-[var(--color-ink)]"
            >
              {ALL_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {STATUS_LABELS[status]}
                </option>
              ))}
            </select>
          </div>

          <div className="flex gap-1">
            {!isClosed && task.scheduled_for !== todayInDisplayTz() ? (
              <button
                type="button"
                disabled={pending}
                onClick={() =>
                  run(() => setScheduleAction(task.id, todayInDisplayTz()))
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

            {confirmingDelete ? (
              <>
                <button
                  type="button"
                  disabled={pending}
                  onClick={() => run(() => deleteTaskAction(task.id))}
                  className="rounded-md border border-[var(--color-danger)] px-2 py-1 text-xs text-[var(--color-danger)]"
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
                className={ICON_BUTTON}
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
