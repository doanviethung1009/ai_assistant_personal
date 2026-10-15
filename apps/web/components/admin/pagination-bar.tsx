import Link from "next/link";

/**
 * Thanh phân trang server-side của trang admin (quy ước 50/trang, `?page=`). `hrefFor` do trang dựng
 * để GIỮ mọi bộ lọc hiện tại trong URL. Luôn hiện tổng số bản ghi; nút Trước/Sau khoá ở đầu/cuối.
 */
export function PaginationBar({
  page,
  total,
  pageSize,
  hrefFor,
}: {
  page: number;
  total: number;
  pageSize: number;
  hrefFor: (page: number) => string;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const current = Math.min(page, totalPages);
  const linkClass =
    "rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm transition hover:bg-[var(--color-surface-hover)]";
  const disabledClass = "cursor-not-allowed rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm opacity-40";
  return (
    <nav aria-label="Phân trang" className="flex items-center justify-between text-sm">
      {current > 1 ? (
        <Link href={hrefFor(current - 1)} className={linkClass}>
          Trang trước
        </Link>
      ) : (
        <span aria-disabled className={disabledClass}>
          Trang trước
        </span>
      )}
      <span className="text-[var(--color-ink-muted)]">
        Trang {current} / {totalPages} · Tổng: {total} kết quả
      </span>
      {current < totalPages ? (
        <Link href={hrefFor(current + 1)} className={linkClass}>
          Trang sau
        </Link>
      ) : (
        <span aria-disabled className={disabledClass}>
          Trang sau
        </span>
      )}
    </nav>
  );
}
