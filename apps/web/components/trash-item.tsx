"use client";

import { useState, useTransition } from "react";

import { purgeTaskAction, restoreTaskAction } from "@/app/actions";
import { PriorityBadge, ProjectBadge, SourceBadge, StatusBadge } from "@/components/badges";
import { formatDateTime } from "@/lib/format";
import { useDisplayTz } from "@/lib/timezone-context";
import type { Task } from "@/lib/types";

const BUTTON =
  "rounded-md border border-[var(--color-border)] px-2.5 py-1 text-xs transition-colors hover:bg-[var(--color-surface-hover)] disabled:opacity-40";

function remainingTone(days: number | null): string {
  if (days === null) return "text-[var(--color-ink-muted)]";
  if (days <= 3) return "text-[var(--color-danger)]";
  if (days <= 7) return "text-[var(--color-warn)]";
  return "text-[var(--color-ink-muted)]";
}

export function TrashItem({ task }: { task: Task }) {
  const tz = useDisplayTz();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  function run(action: () => Promise<{ ok: boolean; error?: string }>) {
    setError(null);
    startTransition(async () => {
      const result = await action();
      if (!result.ok) setError(result.error ?? "Thao tác thất bại");
    });
  }

  const days = task.days_until_purge;

  return (
    <li
      className={`rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3 transition-opacity ${
        pending ? "opacity-60" : ""
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-[var(--color-ink-muted)] line-through">
            {task.title}
          </p>

          {task.description ? (
            <p className="mt-1 line-clamp-1 text-xs text-[var(--color-ink-muted)]">
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
          </div>

          <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--color-ink-muted)]">
            <div className="flex gap-1">
              <dt>Đã xoá:</dt>
              <dd>{formatDateTime(task.deleted_at, tz)}</dd>
            </div>
            <div className="flex gap-1">
              <dt>Xoá vĩnh viễn sau:</dt>
              <dd className={`font-medium ${remainingTone(days)}`}>
                {days === null
                  ? "—"
                  : days === 0
                    ? "sắp tới, ở lần dọn kế tiếp"
                    : `${days} ngày`}
              </dd>
            </div>
          </dl>

          {error ? (
            <p role="alert" className="mt-2 text-xs text-[var(--color-danger)]">
              {error}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 gap-1">
          <button
            type="button"
            disabled={pending}
            onClick={() => run(() => restoreTaskAction(task.id))}
            className={BUTTON}
          >
            Phục hồi
          </button>

          {confirming ? (
            <>
              <button
                type="button"
                disabled={pending}
                onClick={() => run(() => purgeTaskAction(task.id))}
                className="rounded-md border border-[var(--color-danger)] px-2.5 py-1 text-xs text-[var(--color-danger)]"
              >
                Xoá hẳn
              </button>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className={BUTTON}
              >
                Huỷ
              </button>
            </>
          ) : (
            <button
              type="button"
              disabled={pending}
              onClick={() => setConfirming(true)}
              className={BUTTON}
              title="Xoá vĩnh viễn, không hoàn tác được"
            >
              Xoá vĩnh viễn
            </button>
          )}
        </div>
      </div>
    </li>
  );
}
