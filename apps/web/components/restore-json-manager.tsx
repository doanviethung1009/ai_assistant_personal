"use client";

import { useState, useTransition, useRef } from "react";
import { processJsonUploadAction } from "@/app/actions-import";

export function RestoreJsonManager() {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setResult(null);
    const formData = new FormData(e.currentTarget);
    const file = formData.get("file") as File;
    if (!file || file.size === 0) return;

    if (!confirm("BẠN CÓ CHẮC CHẮN? Việc này sẽ ghi đè toàn bộ dữ liệu hiện tại bằng dữ liệu từ file JSON!")) {
      return;
    }

    startTransition(async () => {
      try {
        const res = await processJsonUploadAction(formData);
        if (res.ok) {
          setResult({ ok: true, message: res.message || "Thành công!" });
          formRef.current?.reset();
        } else {
          setResult({ ok: false, message: `Lỗi: ${res.error}` });
        }
      } catch (err: any) {
        setResult({ ok: false, message: `Lỗi đọc file: ${err.message}` });
      }
    });
  };

  return (
    <section className="rounded-lg border border-orange-500/30 bg-orange-500/5 p-4 mt-6">
      <h2 className="text-sm font-semibold text-orange-600 dark:text-orange-400">Khôi phục dữ liệu từ Backup (JSON)</h2>
      <p className="mt-1 text-xs text-orange-600/80 dark:text-orange-400/80 mb-3">
        Tải lên file <b>builder-data.json</b> (hoặc bản backup cũ) để khôi phục lại toàn bộ trạng thái hệ thống. <b>Lưu ý: Thao tác này sẽ ghi đè dữ liệu hiện tại!</b>
      </p>

      <form ref={formRef} onSubmit={handleSubmit} className="relative flex items-center gap-4">
        <input
          type="file"
          name="file"
          accept=".json"
          disabled={pending}
          className="block flex-1 text-sm text-orange-700/80
            file:mr-4 file:py-2 file:px-4
            file:rounded-md file:border-0
            file:text-sm file:font-semibold
            file:bg-orange-500/20 file:text-orange-700
            file:border file:border-orange-500/30
            hover:file:bg-orange-500/30
            disabled:opacity-50 cursor-pointer"
        />
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-orange-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-700 disabled:opacity-50"
        >
          {pending ? "Đang khôi phục..." : "Khôi phục dữ liệu"}
        </button>
      </form>

      {result && (
        <p className={`mt-3 text-sm font-medium ${result.ok ? "text-green-500" : "text-red-500"}`}>
          {result.message}
        </p>
      )}
    </section>
  );
}
