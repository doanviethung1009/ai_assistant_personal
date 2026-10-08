import type { UpsertSummary } from "@/lib/types";

/**
 * Bảng kết quả upsert (added/updated/unchanged/skipped_personal + cảnh báo + lỗi từng dòng).
 *
 * Dùng chung cho nhập Excel và cào URL. Chỉ render text node, không HTML: `reason` có thể
 * chứa nội dung từ file nguồn (untrusted). Danh sách đã được server cắt còn tối đa 20 dòng.
 */
export function UpsertResult({ summary }: { summary: UpsertSummary }) {
  const errors = summary.errors ?? [];
  const warnings = summary.warnings ?? [];
  return (
    <div className="mt-3 text-sm">
      <p className="font-medium text-green-600 dark:text-green-400">
        Thêm mới: {summary.added} · Cập nhật: {summary.updated} · Không đổi: {summary.unchanged}
        {summary.skipped_personal > 0 ? ` · Giữ nguyên ${summary.skipped_personal} task cá nhân` : ""}
        {summary.skipped_no_key ? ` · Bỏ ${summary.skipped_no_key} dòng thiếu Issue Key` : ""}
      </p>
      {warnings.length > 0 && (
        <details className="mt-2 text-xs text-[var(--color-ink-muted)]">
          <summary className="cursor-pointer">Cảnh báo ({summary.warnings_total ?? warnings.length}{(summary.warnings_total ?? 0) > warnings.length ? `; hiện ${warnings.length} đầu` : ""})</summary>
          <ul className="mt-1 list-disc pl-5">
            {warnings.map((w) => (
              <li key={`w${w.index}`}>Dòng {w.index}: {w.reason}</li>
            ))}
          </ul>
        </details>
      )}
      {errors.length > 0 && (
        <details open className="mt-2 text-xs text-[var(--color-danger)]">
          <summary className="cursor-pointer">Lỗi ({summary.errors_total ?? errors.length}{(summary.errors_total ?? 0) > errors.length ? `; hiện ${errors.length} đầu` : ""})</summary>
          <ul className="mt-1 list-disc pl-5">
            {errors.map((e) => (
              <li key={`e${e.index}`}>Dòng {e.index}: {e.reason}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
