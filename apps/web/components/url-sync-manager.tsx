"use client";

import { useState, useTransition } from "react";
import { syncFromUrlAction, addSyncUrlAction, removeSyncUrlAction } from "@/app/actions";

export function UrlSyncManager({ initialUrls }: { initialUrls: string[] }) {
  const [urls, setUrls] = useState<string[]>(initialUrls);
  const [newUrl, setNewUrl] = useState("");
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!newUrl.trim() || urls.includes(newUrl.trim())) return;
    const toAdd = newUrl.trim();
    
    startTransition(async () => {
      await addSyncUrlAction(toAdd);
      setUrls([...urls, toAdd]);
      setNewUrl("");
    });
  }

  function handleRemove(url: string) {
    if (!confirm("Xoá link này?")) return;
    startTransition(async () => {
      await removeSyncUrlAction(url);
      setUrls(urls.filter(u => u !== url));
    });
  }

  function handleSync(url: string) {
    setResult(null);
    startTransition(async () => {
      const res = await syncFromUrlAction(url);
      if (res.ok) {
        setResult({ ok: true, message: `Thành công! Đã cào thêm ${res.count} task mới từ link.` });
      } else {
        setResult({ ok: false, message: `Lỗi: ${res.error}` });
      }
    });
  }

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 mt-6">
      <h2 className="text-sm font-semibold">Tự động cào dữ liệu công việc (Quest Data)</h2>
      <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
        Quản lý các link file Excel (.xlsx) hoặc CSV (.csv). Bạn có thể bấm "Cào" thủ công để đồng bộ ngay lập tức.
      </p>

      <form onSubmit={handleAdd} className="mt-3 flex items-center gap-2">
        <input
          type="url"
          required
          placeholder="https://example.com/path/to/data.xlsx (hoặc .csv)"
          value={newUrl}
          onChange={(e) => setNewUrl(e.target.value)}
          disabled={pending}
          className="flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={pending || !newUrl.trim()}
          className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2 text-sm font-medium transition-colors hover:bg-[var(--color-surface-hover)] disabled:opacity-50"
        >
          Thêm link
        </button>
      </form>

      {urls.length > 0 && (
        <ul className="mt-4 flex flex-col gap-2">
          {urls.map((url) => (
            <li key={url} className="flex items-center justify-between gap-2 rounded-md border border-[var(--color-border)] p-2 text-sm">
              <span className="truncate flex-1 text-[var(--color-ink-muted)]" title={url}>{url}</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleSync(url)}
                  disabled={pending}
                  className="rounded bg-[var(--color-accent)] px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-[var(--color-accent-hover)] disabled:opacity-50"
                >
                  Cào ngay
                </button>
                <button
                  onClick={() => handleRemove(url)}
                  disabled={pending}
                  className="rounded border border-red-500/30 bg-red-500/10 px-3 py-1 text-xs font-medium text-red-600 transition-colors hover:bg-red-500/20 disabled:opacity-50 dark:text-red-400"
                >
                  Xoá
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {result && (
        <p className={`mt-3 text-sm ${result.ok ? "text-green-500" : "text-[var(--color-danger)]"}`}>
          {result.message}
        </p>
      )}
    </section>
  );
}
