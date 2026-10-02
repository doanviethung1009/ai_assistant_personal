"use client";

import { useState, useTransition } from "react";
import { syncChromeHistoryAction } from "@/app/actions-chrome";

export function ChromeHistoryManager() {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [customPath, setCustomPath] = useState("");
  const [showPathInput, setShowPathInput] = useState(false);

  const handleSync = () => {
    setResult(null);
    startTransition(async () => {
      const pathToUse = customPath.trim() || undefined;
      const res = await syncChromeHistoryAction(5000, pathToUse);
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

      {/* Nút toggle hiển thị ô nhập đường dẫn tuỳ chỉnh */}
      <button
        type="button"
        onClick={() => setShowPathInput(!showPathInput)}
        className="mb-3 text-xs text-[var(--color-accent)] hover:underline"
      >
        {showPathInput ? "▾ Ẩn tuỳ chỉnh đường dẫn" : "▸ Tuỳ chỉnh đường dẫn file History (Windows / Profile khác)"}
      </button>

      {showPathInput && (
        <div className="mb-3 flex flex-col gap-2 rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] p-3">
          <label className="text-xs font-medium text-[var(--color-ink-muted)]">
            Đường dẫn tới file <code>History</code> của Chrome:
          </label>
          <input
            type="text"
            value={customPath}
            onChange={(e) => setCustomPath(e.target.value)}
            placeholder="Ví dụ: C:\Users\YourName\AppData\Local\Google\Chrome\User Data\Default\History"
            className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm font-mono placeholder:text-[var(--color-ink-muted)]/50"
          />
          <p className="text-[10px] text-[var(--color-ink-muted)]">
            💡 Để trống nếu muốn dùng đường dẫn mặc định theo hệ điều hành (macOS / Windows / Linux).
            Trên Windows đường dẫn thường là: <code>C:\Users\&lt;Username&gt;\AppData\Local\Google\Chrome\User Data\Default\History</code>
          </p>
        </div>
      )}

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
