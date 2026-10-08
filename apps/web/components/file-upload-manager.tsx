"use client";

import { useState, useTransition, useRef } from "react";
import { importBulkFileAction } from "@/app/actions-import";
import { UpsertResult } from "@/components/upsert-result";
import type { UpsertSummary } from "@/lib/types";

/**
 * Nhập Excel/CSV Jira. `requireSecret` bật ở chế độ api: ghi qua core cần mật khẩu nhập
 * (IMPORT_COMMIT_SECRET), ô này không bao giờ được lưu hay điền sẵn.
 */
export function FileUploadManager({ requireSecret = false }: { requireSecret?: boolean }) {
  const [pending, startTransition] = useTransition();
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
        // Xoá cả ô mật khẩu sau mỗi lần gửi, dù thành công, lỗi hay ném ngoại lệ.
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

      {requireSecret && (
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
        {requireSecret && (
          <input
            type="password"
            name="import_secret"
            required
            autoComplete="new-password"
            placeholder="Mật khẩu nhập dữ liệu"
            disabled={pending}
            className="w-56 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm disabled:opacity-50"
          />
        )}
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
