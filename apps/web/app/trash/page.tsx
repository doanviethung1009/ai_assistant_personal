import { ApiErrorPanel } from "@/components/api-error";
import { TrashActions } from "@/components/trash-actions";
import { TrashItem } from "@/components/trash-item";
import { listTrash } from "@/lib/api";
import type { TrashResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function TrashPage() {
  let trash: TrashResponse;

  try {
    // Lời gọi này cũng dọn luôn task đã quá hạn, vì chưa có scheduler
    trash = await listTrash(200, 0);
  } catch (error) {
    return (
      <ApiErrorPanel
        message={error instanceof Error ? error.message : String(error)}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Thùng rác</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Task đã xoá được giữ {trash.retention_days} ngày rồi xoá vĩnh viễn.
          Trong thời gian đó chúng không xuất hiện ở agenda hay thống kê.
        </p>
      </div>

      {trash.purged_now > 0 ? (
        <p
          role="status"
          className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-2 text-xs text-[var(--color-ink-muted)]"
        >
          Vừa dọn {trash.purged_now} task đã quá {trash.retention_days} ngày.
        </p>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-[var(--color-ink-muted)]">
          {trash.total === 0
            ? "Thùng rác đang trống"
            : `${trash.total} task trong thùng rác`}
        </p>
        <TrashActions total={trash.total} />
      </div>

      {trash.items.length === 0 ? (
        <p className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-ink-muted)]">
          Chưa có task nào bị xoá. Khi bạn xoá task ở trang Hôm nay hoặc Tất cả
          task, nó sẽ nằm ở đây {trash.retention_days} ngày.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {trash.items.map((task) => (
            <TrashItem key={task.id} task={task} />
          ))}
        </ul>
      )}

      <section className="rounded-lg border border-dashed border-[var(--color-border)] p-4">
        <h2 className="text-sm font-semibold">Về việc dọn tự động</h2>
        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Hệ thống chưa có scheduler, nên việc dọn quá hạn xảy ra ở hai thời
          điểm: khi khởi động store, và mỗi lần bạn mở trang này. Không có task
          nào bị xoá sớm hơn {trash.retention_days} ngày, nhưng có thể bị xoá
          muộn hơn nếu lâu không mở app. Khi scheduler xuất hiện ở Phase 2, cho
          nó gọi <code>POST /api/v1/tasks/trash/purge</code> mỗi ngày.
        </p>
        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Đổi thời hạn giữ bằng biến <code>TRASH_RETENTION_DAYS</code>. Đặt{" "}
          <code>0</code> nghĩa là xoá thẳng, không qua thùng rác.
        </p>
      </section>
    </div>
  );
}
