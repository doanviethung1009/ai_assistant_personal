"use client";

import { useActionAuth } from "@/lib/use-action-auth";
import { useState, useTransition, useRef } from "react";
import { importBulkFileAction } from "@/app/actions-import";
import { UpsertResult } from "@/components/upsert-result";
import type { UpsertSummary } from "@/lib/types";

/**
 * Nhập Excel/CSV Jira. `apiMode` bật ở chế độ api: dữ liệu ghi vào Postgres qua core, quyền
 * ghi do core kiểm theo role nên không có ô mật khẩu.
 */
export function FileUploadManager({ apiMode = false }: { apiMode?: boolean }) {
  const [pending, startTransition] = useTransition();
  const gate = useActionAuth();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [summary, setSummary] = useState<UpsertSummary | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setResult(null);
    setSummary(null);
    const formData = new FormData(e.currentTarget);
    const file = formData.get("file") as File;
    if (!file || file.size === 0) return;

    startTransition(async () => {
      try {
        const res = await importBulkFileAction(formData);
        if (gate(res)) return;
        if (res.ok) {
          const skipped = res.skipped_personal > 0 ? `, giữ nguyên ${res.skipped_personal} task cá nhân` : "";
          setResult({ ok: true, message: `Thành công! Đã phân tích file ${file.name}. Thêm mới: ${res.added}, Cập nhật: ${res.updated} tasks${skipped}.` });
          if (res.summary) setSummary(res.summary);
        } else {
          setResult({ ok: false, message: `Lỗi: ${res.error}` });
        }
      } catch {
        setResult({ ok: false, message: "Lỗi gửi file lên server." });
      } finally {
        // Xoá ô chọn file sau mỗi lần gửi, dù thành công, lỗi hay ném ngoại lệ.
        formRef.current?.reset();
      }
    });
  };

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 mt-6">
      <h2 className="text-sm font-semibold">Tải lên file trực tiếp (Manual Upload)</h2>
      <p className="mt-1 text-xs text-[var(--color-ink-muted)] mb-3">
        Tải file <b>.xlsx</b> hoặc <b>.csv</b> lên đây để đồng bộ ngay lập tức. Tính năng này được xử lý trực tiếp trên server nên sẽ không gây giật lag trình duyệt.
      </p>

      {apiMode && (
        <p className="mb-3 text-xs text-[var(--color-ink-muted)]">
          Chế độ api: dữ liệu ghi vào Postgres theo khoá Issue Key (nguồn <code>jira</code>), chạy lại không nhân đôi.
          Task cá nhân trùng khoá được giữ nguyên; dòng thiếu Issue Key bị bỏ qua.
        </p>
      )}
      <form ref={formRef} onSubmit={handleSubmit} className="relative flex flex-wrap items-center gap-4">
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
      {summary && <UpsertResult summary={summary} />}
    </section>
  );
}
