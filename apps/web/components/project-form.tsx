"use client";

import { useRef, useState, useTransition } from "react";

import { createProjectAction } from "@/app/actions";

const INPUT_CLASS =
  "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm";
const LABEL_CLASS = "mb-1 block text-xs font-medium text-[var(--color-ink-muted)]";

export function ProjectForm() {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const formRef = useRef<HTMLFormElement>(null);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const form = new FormData(event.currentTarget);
    const key = String(form.get("key") ?? "");
    const name = String(form.get("name") ?? "");
    const color = String(form.get("color") ?? "");

    startTransition(async () => {
      const result = await createProjectAction(key, name, color || undefined);
      if (result.ok) {
        formRef.current?.reset();
      } else {
        setError(result.error ?? "Tạo project thất bại");
      }
    });
  }

  return (
    <form
      ref={formRef}
      onSubmit={handleSubmit}
      className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4"
      aria-label="Thêm project"
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[140px_1fr_120px_auto] sm:items-end">
        <div>
          <label htmlFor="project-key" className={LABEL_CLASS}>
            Mã
          </label>
          <input
            id="project-key"
            name="key"
            type="text"
            required
            maxLength={20}
            pattern="[A-Za-z][A-Za-z0-9_]{1,19}"
            title="2-20 ký tự, bắt đầu bằng chữ, chỉ chữ số và dấu gạch dưới"
            placeholder="HOMELAB"
            className={`${INPUT_CLASS} uppercase`}
          />
        </div>

        <div>
          <label htmlFor="project-name" className={LABEL_CLASS}>
            Tên
          </label>
          <input
            id="project-name"
            name="name"
            type="text"
            required
            maxLength={200}
            placeholder="Home lab migration"
            className={INPUT_CLASS}
          />
        </div>

        <div>
          <label htmlFor="project-color" className={LABEL_CLASS}>
            Màu
          </label>
          <input
            id="project-color"
            name="color"
            type="color"
            defaultValue="#4f8cff"
            className="h-[38px] w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-1"
          />
        </div>

        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {pending ? "Đang lưu…" : "Thêm"}
        </button>
      </div>

      {error ? (
        <p role="alert" className="mt-2 text-sm text-[var(--color-danger)]">
          {error}
        </p>
      ) : null}
    </form>
  );
}
