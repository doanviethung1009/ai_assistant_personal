/** Khung chờ cho bảng quản trị: tiêu đề và bộ lọc hiện ngay, chỉ phần bảng chờ core. */
export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="animate-pulse space-y-2" aria-busy="true" aria-label="Đang tải">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-14 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)]" />
      ))}
    </div>
  );
}
