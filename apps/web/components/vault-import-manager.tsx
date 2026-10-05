"use client";

import { useRef, useState, useTransition } from "react";
import { importVaultAction } from "@/app/vault-actions";

export function VaultImportManager() {
  const [result, setResult] = useState<{ ok: boolean; error?: string } | null>(null);
  const [pending, startTransition] = useTransition();
  const formRef = useRef<HTMLFormElement>(null);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(null);

    const formData = new FormData(event.currentTarget);

    startTransition(async () => {
      const response = await importVaultAction(formData);
      setResult(response);
      if (response.ok) {
        formRef.current?.reset();
        alert("Đã nhập két bảo mật thành công!");
      }
    });
  }

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 mt-6">
      <h2 className="text-sm font-semibold">Nhập Két bảo mật (Vault)</h2>
      <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
        Phục hồi lại Két từ file JSON sao lưu. <b>Lưu ý:</b> Dữ liệu Két hiện tại (nếu có) sẽ bị ghi đè hoàn toàn.
      </p>

      <form ref={formRef} onSubmit={handleSubmit} className="mt-4 flex flex-col gap-3">
        <div>
          <label htmlFor="vault-import-file" className="mb-1 block text-xs font-medium text-[var(--color-ink-muted)]">
            File Két (JSON)
          </label>
          <input
            id="vault-import-file"
            name="file"
            type="file"
            required
            accept=".json,application/json"
            className="w-full max-w-sm rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm file:mr-3 file:rounded file:border-0 file:bg-[var(--color-surface-hover)] file:px-2 file:py-1 file:text-xs file:text-[var(--color-ink)]"
          />
        </div>
        
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" name="confirm" value="yes" required className="accent-[var(--color-danger)]" />
          <span className="text-[var(--color-danger)]">Tôi hiểu rằng két hiện tại sẽ bị xoá và ghi đè.</span>
        </label>

        <div>
          <button
            type="submit"
            disabled={pending}
            className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {pending ? "Đang nhập…" : "Nhập Két"}
          </button>
        </div>
      </form>

      {result && !result.ok ? (
        <p className="mt-3 text-sm text-[var(--color-danger)]">{result.error}</p>
      ) : null}
    </section>
  );
}
