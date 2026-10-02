"use client";

import { useState, useTransition } from "react";
import { syncChromeHistoryAction } from "@/app/actions-chrome";

export function ChromeHistoryManager() {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  const handleSync = () => {
    setResult(null);
    startTransition(async () => {
      const res = await syncChromeHistoryAction(5000); // Lấy 5000 lịch sử gần nhất
      if (res.ok) {
        setResult({ ok: true, message: `Thành công! Đã trích xuất ${res.count} dòng lịch sử web. Lưu tại: ${res.path}` });
      } else {
        setResult({ ok: false, message: `Lỗi: ${res.error}` });
      }
    });
  };

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 mt-6">
      <h2 className="text-sm font-semibold">Đồng bộ Lịch sử Google Chrome</h2>
      <p className="mt-1 text-xs text-[var(--color-ink-muted)] mb-3">
        Tự động copy dữ liệu lịch sử duyệt web (Google Chrome) trên máy tính này và trích xuất thành file JSON độc lập <code>(data/chrome-history.json)</code> để phân tích sau.
      </p>

      <button
        onClick={handleSync}
        disabled={pending}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
      >
        {pending ? "Đang trích xuất..." : "Trích xuất Chrome History"}
      </button>

      {result && (
        <p className={`mt-3 text-sm font-medium ${result.ok ? "text-green-500" : "text-[var(--color-danger)]"}`}>
          {result.message}
        </p>
      )}
    </section>
  );
}
