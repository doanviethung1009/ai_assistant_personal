"use client";

import { useRef, useState, useTransition } from "react";

import { createTaskAction, type NewTaskInput } from "@/app/actions";
import {
  PRIORITY_LABELS,
  SCOPE_LABELS,
  STATUS_LABELS,
  type Project,
  type TaskPriority,
  type TaskScope,
  type TaskStatus,
} from "@/lib/types";

const INPUT_CLASS =
  "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-ink)] placeholder:text-[var(--color-ink-muted)]";
const LABEL_CLASS = "mb-1 block text-xs font-medium text-[var(--color-ink-muted)]";

function todayLocalIso(): string {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10);
}

export function QuickAddForm({
  projects,
  defaultScheduleToday = false,
  defaultScope = "personal",
}: {
  projects: Project[];
  defaultScheduleToday?: boolean;
  /** Task tạo tay mặc định là việc riêng; tab Công việc ở /tasks đổi thành `work`. */
  defaultScope?: TaskScope;
}) {
  const [scope, setScope] = useState<TaskScope>(defaultScope);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const formRef = useRef<HTMLFormElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const form = new FormData(event.currentTarget);
    const title = String(form.get("title") ?? "").trim();
    if (!title) {
      setError("Nhập tiêu đề trước đã");
      titleRef.current?.focus();
      return;
    }

    // datetime-local không mang timezone. Quy đổi bằng Date của browser để
    // gửi lên ISO có offset đúng, backend lưu UTC.
    const dueLocal = String(form.get("due_at") ?? "");
    const dueAt = dueLocal ? new Date(dueLocal).toISOString() : undefined;

    const estimateRaw = String(form.get("estimate_minutes") ?? "");
    const estimate = estimateRaw ? Number.parseInt(estimateRaw, 10) : undefined;

    const tagsRaw = String(form.get("tags") ?? "");
    const tags = tagsRaw
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);

    const payload: NewTaskInput = {
      title,
      description: String(form.get("description") ?? "") || undefined,
      status: (String(form.get("status") ?? "todo") as TaskStatus) || "todo",
      priority: (String(form.get("priority") ?? "medium") as TaskPriority) || "medium",
      projectId: String(form.get("project_id") ?? "") || undefined,
      dueAt,
      scheduledFor: String(form.get("scheduled_for") ?? "") || undefined,
      estimateMinutes:
        estimate !== undefined && Number.isFinite(estimate) && estimate > 0
          ? estimate
          : undefined,
      tags,
      scope,
    };

    startTransition(async () => {
      const result = await createTaskAction(payload);
      if (result.ok) {
        formRef.current?.reset();
        setExpanded(false);
        titleRef.current?.focus();
      } else {
        setError(result.error ?? "Tạo task thất bại");
      }
    });
  }

  return (
    <form
      ref={formRef}
      onSubmit={handleSubmit}
      className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4"
      aria-label="Thêm task mới"
    >
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="flex-1">
          <label htmlFor="task-title" className="sr-only">
            Tiêu đề task
          </label>
          <input
            ref={titleRef}
            id="task-title"
            name="title"
            type="text"
            required
            maxLength={500}
            autoComplete="off"
            placeholder="Việc cần làm là gì?"
            className={INPUT_CLASS}
            aria-describedby={error ? "task-error" : undefined}
          />
        </div>

        <div
          role="radiogroup"
          aria-label="Loại task"
          className="flex overflow-hidden rounded-md border border-[var(--color-border)] text-sm"
        >
          {(["personal", "work"] as TaskScope[]).map((value) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={scope === value}
              onClick={() => setScope(value)}
              className={`px-3 py-2 transition-colors ${
                scope === value
                  ? "bg-[var(--color-accent)] text-white"
                  : "text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-hover)]"
              }`}
            >
              {SCOPE_LABELS[value]}
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            aria-expanded={expanded}
            aria-controls="task-details"
            className="rounded-md border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-ink-muted)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink)]"
          >
            {expanded ? "Ẩn chi tiết" : "Chi tiết"}
          </button>
          <button
            type="submit"
            disabled={pending}
            className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white transition-opacity disabled:opacity-50"
          >
            {pending ? "Đang lưu…" : "Thêm"}
          </button>
        </div>
      </div>

      {error ? (
        <p
          id="task-error"
          role="alert"
          className="mt-2 text-sm text-[var(--color-danger)]"
        >
          {error}
        </p>
      ) : null}

      {expanded ? (
        <div
          id="task-details"
          className="mt-4 grid grid-cols-1 gap-3 border-t border-[var(--color-border)] pt-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          <div className="sm:col-span-2 lg:col-span-3">
            <label htmlFor="task-description" className={LABEL_CLASS}>
              Mô tả
            </label>
            <textarea
              id="task-description"
              name="description"
              rows={3}
              className={INPUT_CLASS}
              placeholder="Ghi chú, bối cảnh, tiêu chí hoàn thành…"
            />
          </div>

          <div>
            <label htmlFor="task-project" className={LABEL_CLASS}>
              Dự án
            </label>
            <select id="task-project" name="project_id" className={INPUT_CLASS}>
              <option value="">Không thuộc dự án</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.key} — {project.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="task-status" className={LABEL_CLASS}>
              Trạng thái
            </label>
            <select
              id="task-status"
              name="status"
              defaultValue="todo"
              className={INPUT_CLASS}
            >
              {(
                ["backlog", "todo", "in_progress", "blocked"] as TaskStatus[]
              ).map((status) => (
                <option key={status} value={status}>
                  {STATUS_LABELS[status]}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="task-priority" className={LABEL_CLASS}>
              Ưu tiên
            </label>
            <select
              id="task-priority"
              name="priority"
              defaultValue="medium"
              className={INPUT_CLASS}
            >
              {(["low", "medium", "high", "urgent"] as TaskPriority[]).map(
                (priority) => (
                  <option key={priority} value={priority}>
                    {PRIORITY_LABELS[priority]}
                  </option>
                ),
              )}
            </select>
          </div>

          <div>
            <label htmlFor="task-scheduled" className={LABEL_CLASS}>
              Ngày dự định làm
            </label>
            <input
              id="task-scheduled"
              name="scheduled_for"
              type="date"
              defaultValue={defaultScheduleToday ? todayLocalIso() : undefined}
              className={INPUT_CLASS}
            />
          </div>

          <div>
            <label htmlFor="task-due" className={LABEL_CLASS}>
              Hạn chót
            </label>
            <input
              id="task-due"
              name="due_at"
              type="datetime-local"
              className={INPUT_CLASS}
            />
          </div>

          <div>
            <label htmlFor="task-estimate" className={LABEL_CLASS}>
              Ước lượng (phút)
            </label>
            <input
              id="task-estimate"
              name="estimate_minutes"
              type="number"
              min={1}
              step={5}
              className={INPUT_CLASS}
              placeholder="30"
            />
          </div>

          <div className="sm:col-span-2 lg:col-span-3">
            <label htmlFor="task-tags" className={LABEL_CLASS}>
              Tag, cách nhau bằng dấu phẩy
            </label>
            <input
              id="task-tags"
              name="tags"
              type="text"
              className={INPUT_CLASS}
              placeholder="deploy, homelab, review"
            />
          </div>
        </div>
      ) : null}
    </form>
  );
}
