import { ApiErrorPanel } from "@/components/api-error";
import { TrashActions } from "@/components/trash-actions";
import { TrashItem } from "@/components/trash-item";
import { TrashNoteActions } from "@/components/trash-note-actions";
import { TrashNoteItem } from "@/components/trash-note-item";
import { listNoteTrash, listTrash } from "@/lib/api";
import type { NoteTrashResponse, TrashResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function TrashPage() {
  let trash: TrashResponse;
  let noteTrash: NoteTrashResponse;

  try {
    // Hai lời gọi này cũng dọn luôn bản ghi đã quá hạn, vì chưa có scheduler.
    // Chạy song song vì chúng độc lập với nhau.
    [trash, noteTrash] = await Promise.all([
      listTrash(200, 0),
      listNoteTrash(200, 0),
    ]);
  } catch (error) {
    return (
      <ApiErrorPanel
        message={error instanceof Error ? error.message : String(error)}
      />
    );
  }

  const purgedNow = trash.purged_now + noteTrash.purged_now;
  const retention = trash.retention_days;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Thùng rác</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Task và mục sổ tay đã xoá được giữ {retention} ngày rồi xoá vĩnh viễn.
          Trong thời gian đó chúng không xuất hiện ở agenda, thống kê hay kết
          quả tìm kiếm.
        </p>
      </div>

      {purgedNow > 0 ? (
        <p
          role="status"
          className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-2 text-xs text-[var(--color-ink-muted)]"
        >
          Vừa dọn {purgedNow} bản ghi đã quá {retention} ngày.
        </p>
      ) : null}

      {/* ── Task ─────────────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold">
            Task{" "}
            <span className="text-sm font-normal text-[var(--color-ink-muted)]">
              ({trash.total})
            </span>
          </h2>
          <TrashActions total={trash.total} />
        </div>

        {trash.items.length === 0 ? (
          <p className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-ink-muted)]">
            Chưa có task nào bị xoá. Khi bạn xoá task ở trang Hôm nay hoặc Tất
            cả task, nó sẽ nằm ở đây {retention} ngày.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {trash.items.map((task) => (
              <TrashItem key={task.id} task={task} />
            ))}
          </ul>
        )}
      </section>

      {/* ── Sổ tay ───────────────────────────────────────────────────── */}
      <section className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold">
            Sổ tay{" "}
            <span className="text-sm font-normal text-[var(--color-ink-muted)]">
              ({noteTrash.total})
            </span>
          </h2>
          <TrashNoteActions total={noteTrash.total} />
        </div>

        {noteTrash.items.length === 0 ? (
          <p className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-ink-muted)]">
            Chưa có mục sổ tay nào bị xoá. Khi bạn xoá một câu lệnh ở trang Sổ
            tay, nó sẽ nằm ở đây {noteTrash.retention_days} ngày.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {noteTrash.items.map((note) => (
              <TrashNoteItem key={note.id} note={note} />
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-lg border border-dashed border-[var(--color-border)] p-4">
        <h2 className="text-sm font-semibold">Về việc dọn tự động</h2>
        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Hệ thống chưa có scheduler, nên việc dọn quá hạn xảy ra ở hai thời
          điểm: khi khởi động store, và mỗi lần bạn mở trang này. Không có bản
          ghi nào bị xoá sớm hơn {retention} ngày, nhưng có thể bị xoá muộn hơn
          nếu lâu không mở app. Khi scheduler xuất hiện ở Phase 2, cho nó gọi{" "}
          <code>POST /api/v1/tasks/trash/purge</code> và{" "}
          <code>POST /api/v1/notes/trash/purge</code> mỗi ngày.
        </p>
        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Đổi thời hạn giữ bằng biến <code>TRASH_RETENTION_DAYS</code>. Nó áp
          dụng cho cả task và sổ tay. Đặt <code>0</code> nghĩa là xoá thẳng,
          không qua thùng rác.
        </p>
      </section>
    </div>
  );
}
