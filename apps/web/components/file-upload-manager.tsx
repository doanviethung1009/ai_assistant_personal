"use client";

import { useState, useTransition, useRef } from "react";
import { importBulkFileAction } from "@/app/actions-import";

export function FileUploadManager() {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setResult(null);
    const formData = new FormData(e.currentTarget);
    const file = formData.get("file") as File;
    if (!file || file.size === 0) return;

    startTransition(async () => {
      try {
        const res = await importBulkFileAction(formData);
        if (res.ok && "added" in res) {
          setResult({ ok: true, message: `Thành công! Đã phân tích file ${file.name}. Thêm mới: ${res.added}, Cập nhật: ${res.updated} tasks.` });
          formRef.current?.reset();
        } else {
          setResult({ ok: false, message: `Lỗi: ${"error" in res ? res.error : "Unknown error"}` });
        }
      } catch (err: any) {
        setResult({ ok: false, message: `Lỗi đọc file: ${err.message}` });
      }
    });
  };

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 mt-6">
      <h2 className="text-sm font-semibold">Tải lên file trực tiếp (Manual Upload)</h2>
      <p className="mt-1 text-xs text-[var(--color-ink-muted)] mb-3">
        Tải file <b>.xlsx</b> hoặc <b>.csv</b> lên đây để đồng bộ ngay lập tức. Tính năng này được xử lý trực tiếp trên server nên sẽ không gây giật lag trình duyệt.
      </p>

      <form ref={formRef} onSubmit={handleSubmit} className="relative flex items-center gap-4">
        <input
          type="file"
          name="file"
          accept=".xlsx, .xls, .csv"
          disabled={pending}
          className="block flex-1 text-sm text-[var(--color-ink-muted)]
            file:mr-4 file:py-2 file:px-4
            file:rounded-md file:border-0
            file:text-sm file:font-semibold
            file:bg-[var(--color-surface)] file:text-[var(--color-ink)]
            file:border file:border-[var(--color-border)]
            hover:file:bg-[var(--color-surface-hover)]
            disabled:opacity-50 cursor-pointer"
        />
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
        >
          {pending ? "Đang xử lý..." : "Tải lên & Phân tích"}
        </button>
      </form>

      {result && (
        <p className={`mt-3 text-sm font-medium ${result.ok ? "text-green-500" : "text-[var(--color-danger)]"}`}>
          {result.message}
        </p>
      )}
    </section>
  );
}
