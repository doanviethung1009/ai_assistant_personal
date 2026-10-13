/**
 * Skeleton hiện ngay khi điều hướng/lọc ở chế độ server, thay vì để trang đứng yên chờ render.
 * Next tự bọc page trong <Suspense> với fallback này.
 */
export default function Loading() {
  return (
    <div className="mx-auto flex w-full max-w-none animate-pulse flex-col gap-6 pb-12" aria-busy="true" aria-label="Đang tải">
      <div className="h-9 w-64 rounded-lg bg-[var(--color-surface-hover)]" />
      <div className="h-40 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-raised)]" />
      <div className="flex flex-col gap-2">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="h-16 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)]" />
        ))}
      </div>
    </div>
  );
}
