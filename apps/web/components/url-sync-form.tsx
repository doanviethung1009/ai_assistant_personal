"use client";

import { useState, useTransition } from "react";
import { syncFromUrlAction } from "@/app/actions";

export function UrlSyncForm() {
  const [url, setUrl] = useState("");
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  function handleSync(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;

    setResult(null);
    startTransition(async () => {
      const res = await syncFromUrlAction(url.trim());
      if (res.ok) {
        setResult({ ok: true, message: `Thành công! Đã cào thêm ${res.count} task mới.` });
        setUrl("");
      } else {
        setResult({ ok: false, message: `Lỗi: ${res.error}` });
      }
    });
  }

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 mt-6">
      <h2 className="text-sm font-semibold">Tự động cào dữ liệu công việc (Quest Data)</h2>
      <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
        Nhập link đến file Excel (.xlsx) hoặc CSV (.csv) chứa danh sách ticket Jira của bạn. Hệ thống sẽ đọc file và tự động tạo task (bỏ qua những task đã tồn tại).
      </p>

      <form onSubmit={handleSync} className="mt-3 flex items-center gap-2">
        <input
          type="url"
          required
          placeholder="https://example.com/path/to/data.xlsx (hoặc .csv)"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={pending}
          className="w-full max-w-md rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={pending || !url.trim()}
          className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
        >
          {pending ? "Đang cào..." : "Cào dữ liệu"}
        </button>
      </form>

      {result && (
        <p className={`mt-3 text-sm ${result.ok ? "text-green-500" : "text-[var(--color-danger)]"}`}>
          {result.message}
        </p>
      )}
    </section>
  );
}
