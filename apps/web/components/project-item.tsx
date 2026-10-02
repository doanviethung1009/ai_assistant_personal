"use client";

import { useState, useTransition } from "react";
import { updateProjectAction, deleteProjectAction } from "@/app/actions";
import type { Project } from "@/lib/types";

const INPUT_CLASS =
  "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm";
const LABEL_CLASS = "mb-1 block text-xs font-medium text-[var(--color-ink-muted)]";

export function ProjectItem({ project }: { project: Project }) {
  const [isEditing, setIsEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function handleUpdate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const form = new FormData(event.currentTarget);
    const key = String(form.get("key") ?? "");
    const name = String(form.get("name") ?? "");
    const description = String(form.get("description") ?? "");
    const color = String(form.get("color") ?? "");
    const is_archived = form.has("is_archived");

    startTransition(async () => {
      const result = await updateProjectAction(project.id, {
        key,
        name,
        description: description || null,
        color: color || null,
        is_archived
      });
      if (result.ok) {
        setIsEditing(false);
      } else {
        setError(result.error ?? "Cập nhật project thất bại");
      }
    });
  }

  function handleDelete() {
    if (!window.confirm(`Bạn có chắc muốn xoá dự án ${project.key}? Task thuộc dự án này sẽ bị gỡ liên kết.`)) return;
    startTransition(async () => {
      const result = await deleteProjectAction(project.id);
      if (!result.ok) {
        alert(result.error ?? "Xoá project thất bại");
      }
    });
  }

  if (isEditing) {
    return (
      <li className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4">
        <form onSubmit={handleUpdate} className="flex flex-col gap-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-[140px_1fr_120px]">
            <div>
              <label className={LABEL_CLASS}>Mã</label>
              <input
                name="key"
                type="text"
                required
                maxLength={20}
                pattern="[A-Za-z][A-Za-z0-9_]{1,19}"
                defaultValue={project.key}
                className={`${INPUT_CLASS} uppercase`}
              />
            </div>
            <div>
              <label className={LABEL_CLASS}>Tên</label>
              <input
                name="name"
                type="text"
                required
                maxLength={200}
                defaultValue={project.name}
                className={INPUT_CLASS}
              />
            </div>
            <div>
              <label className={LABEL_CLASS}>Màu</label>
              <input
                name="color"
                type="color"
                defaultValue={project.color ?? "#4f8cff"}
                className="h-[38px] w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-1"
              />
            </div>
          </div>
          <div>
            <label className={LABEL_CLASS}>Mô tả</label>
            <input
              name="description"
              type="text"
              maxLength={500}
              defaultValue={project.description ?? ""}
              className={INPUT_CLASS}
            />
          </div>
          <div className="flex items-center gap-2 mt-1">
            <input type="checkbox" id={`archive-${project.id}`} name="is_archived" defaultChecked={project.is_archived} />
            <label htmlFor={`archive-${project.id}`} className="text-sm">Đã lưu trữ</label>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <button
              type="submit"
              disabled={pending}
              className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {pending ? "Đang lưu…" : "Lưu"}
            </button>
            <button
              type="button"
              onClick={() => setIsEditing(false)}
              className="rounded-md border border-[var(--color-border)] px-4 py-2 text-sm disabled:opacity-50"
            >
              Huỷ
            </button>
          </div>
          {error && <p className="text-sm text-[var(--color-danger)]">{error}</p>}
        </form>
      </li>
    );
  }

  return (
    <li className="flex items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3">
      <span
        aria-hidden="true"
        className="size-3 shrink-0 rounded-full"
        style={{ backgroundColor: project.color ?? "#4f8cff" }}
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          <span className="text-[var(--color-ink-muted)]">
            {project.key}
          </span>{" "}
          {project.name}
        </p>
        {project.description ? (
          <p className="text-xs text-[var(--color-ink-muted)]">
            {project.description}
          </p>
        ) : null}
      </div>
      {project.is_archived ? (
        <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs text-[var(--color-ink-muted)]">
          đã lưu trữ
        </span>
      ) : null}
      <div className="flex items-center gap-2 ml-4">
        <button
          onClick={() => setIsEditing(true)}
          className="text-xs font-medium text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
        >
          Sửa
        </button>
        <button
          onClick={handleDelete}
          disabled={pending}
          className="text-xs font-medium text-[var(--color-danger)] opacity-80 hover:opacity-100 disabled:opacity-50"
        >
          {pending ? "..." : "Xoá"}
        </button>
      </div>
    </li>
  );
}
