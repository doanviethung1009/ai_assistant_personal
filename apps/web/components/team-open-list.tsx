"use client";

import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { TaskItem } from "@/components/task-item";
import { OPEN_STATUSES, type Task } from "@/lib/types";

/** Nhóm task công việc chưa có người nhận. */
const UNASSIGNED = "Chưa giao";
/** Tối đa 200/trang ở chế độ này để không hydrate hàng trăm TaskItem một lúc. */
const SIZES = [50, 100, 200] as const;
const DAY_MS = 24 * 60 * 60 * 1000;
const TIME_PRESETS = [
  { id: "all", label: "Tất cả", days: 0 },
  { id: "1d", label: "1 ngày qua", days: 1 },
  { id: "3d", label: "3 ngày qua", days: 3 },
  { id: "7d", label: "7 ngày qua", days: 7 },
  { id: "30d", label: "30 ngày qua", days: 30 },
] as const;
const SORTS = [
  { id: "all", label: "Tất cả" },
  { id: "newest", label: "Mới nhất" },
  { id: "oldest", label: "Cũ nhất" },
] as const;

export interface TeamFilters {
  assignee: string;
  sort: string;
  q: string;
  time: string;
  from: string;
  to: string;
  size: number;
  page: number;
}

const CHIP_ON = "bg-[var(--color-accent)] text-white";
const CHIP_OFF =
  "border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)]";
const INPUT =
  "rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-0.5 text-xs text-[var(--color-ink)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]";

/** Mốc thời gian dùng để lọc: task đóng theo completed_at, task mở theo updated_at. */
function activityMs(t: Task): number {
  const closed = !OPEN_STATUSES.includes(t.status);
  const s = closed && t.completed_at ? t.completed_at : t.updated_at || t.created_at;
  if (!s) return 0;
  const ms = new Date(s).getTime();
  return Number.isNaN(ms) ? 0 : ms;
}

/**
 * Danh sách task ĐANG MỞ của team, lọc hoàn toàn trong browser.
 *
 * Vì sao có: tập task đang mở nhỏ (server chỉ giao xuống khi ≤ ngưỡng), nên mọi filter
 * (người làm, từ khoá, mốc thời gian, sắp xếp, phân trang) chạy tức thì bằng React, không
 * render lại server và không tốn request vào core. Chỉ khi xem task đã đóng/tất cả mới
 * điều hướng sang chế độ server (phân trang thật). `nowMs` do server truyền để server và
 * client tính cùng một mốc, tránh lệch hydration ở ranh "N ngày qua".
 *
 * Filter đồng bộ lên URL bằng history.replaceState (không kích hoạt render server), nên
 * refresh hay chia sẻ link vẫn giữ nguyên bộ lọc.
 */
export function TeamOpenList({
  tasks,
  initial,
  nowMs,
}: {
  tasks: Task[];
  initial: TeamFilters;
  nowMs: number;
}) {
  const router = useRouter();
  const [f, setF] = useState<TeamFilters>(initial);
  // Ô gõ giữ giá trị tức thời, danh sách dùng giá trị trễ để gõ không bị khựng.
  const deferred = useDeferredValue(f);
  const stale = deferred !== f;
  const topRef = useRef<HTMLDivElement>(null);

  function update(patch: Partial<TeamFilters>, keepPage = false) {
    setF((prev) => ({ ...prev, ...patch, page: keepPage ? (patch.page ?? prev.page) : 1 }));
  }

  // Đồng bộ URL, bỏ giá trị mặc định cho gọn.
  useEffect(() => {
    const q = new URLSearchParams();
    if (f.assignee) q.set("assignee", f.assignee);
    if (f.sort !== "all") q.set("sort", f.sort);
    if (f.q) q.set("q", f.q);
    if (f.time !== "all") q.set("time", f.time);
    if (f.from) q.set("from", f.from);
    if (f.to) q.set("to", f.to);
    if (f.size !== 50) q.set("size", String(f.size));
    if (f.page > 1) q.set("page", String(f.page));
    const qs = q.toString();
    window.history.replaceState(null, "", qs ? `/team?${qs}` : "/team");
  }, [f]);

  const { visible, total, totalPages, assigneeCounts, assignees, page } = useMemo(() => {
    let list = tasks.filter((t) => OPEN_STATUSES.includes(t.status));

    const needle = deferred.q.trim().toLowerCase();
    if (needle) {
      list = list.filter(
        (t) =>
          t.title.toLowerCase().includes(needle) ||
          t.tags.some((tag) => tag.toLowerCase().includes(needle)),
      );
    }
    const preset = TIME_PRESETS.find((p) => p.id === deferred.time);
    if (preset && preset.days > 0) {
      const limit = nowMs - preset.days * DAY_MS;
      list = list.filter((t) => activityMs(t) >= limit);
    }
    if (deferred.from) {
      const fromMs = new Date(deferred.from).getTime();
      if (!Number.isNaN(fromMs)) list = list.filter((t) => activityMs(t) >= fromMs);
    }
    if (deferred.to) {
      const toMs = new Date(deferred.to).getTime() + DAY_MS - 1;
      if (!Number.isNaN(toMs)) list = list.filter((t) => activityMs(t) <= toMs);
    }

    // Số theo người tính TRƯỚC khi lọc người, nhưng liệt kê đủ mọi người (kể cả 0).
    const counts: Record<string, number> = {};
    for (const t of tasks) counts[t.assignee || UNASSIGNED] = 0;
    for (const t of list) {
      const name = t.assignee || UNASSIGNED;
      counts[name] = (counts[name] ?? 0) + 1;
    }

    if (deferred.assignee) {
      list =
        deferred.assignee === UNASSIGNED
          ? list.filter((t) => !t.assignee)
          : list.filter((t) => t.assignee === deferred.assignee);
    }
    if (deferred.sort !== "all") {
      const dir = deferred.sort === "newest" ? -1 : 1;
      list = [...list].sort(
        (a, b) => dir * (new Date(a.created_at).getTime() - new Date(b.created_at).getTime()),
      );
    }

    const pages = Math.max(1, Math.ceil(list.length / deferred.size));
    const p = Math.min(deferred.page, pages);
    return {
      visible: list.slice((p - 1) * deferred.size, p * deferred.size),
      total: list.length,
      totalPages: pages,
      assigneeCounts: counts,
      assignees: Object.keys(counts).sort(),
      page: p,
    };
  }, [tasks, deferred, nowMs]);

  // Dữ liệu đổi (sửa/đóng task) có thể làm trang hiện tại vượt tổng: kéo state và URL về trang hợp lệ.
  useEffect(() => {
    if (page !== f.page) setF((prev) => ({ ...prev, page }));
  }, [page, f.page]);

  function goPage(next: number) {
    update({ page: next }, true);
    topRef.current?.scrollIntoView({ block: "start" });
  }

  /** Sang chế độ server nhưng giữ nguyên bộ lọc hiện có (trừ trang). */
  function goServer(status: "closed" | "all") {
    const q = new URLSearchParams({ status });
    if (f.assignee) q.set("assignee", f.assignee);
    if (f.sort !== "all") q.set("sort", f.sort);
    if (f.q) q.set("q", f.q);
    if (f.time !== "all") q.set("time", f.time);
    if (f.from) q.set("from", f.from);
    if (f.to) q.set("to", f.to);
    if (f.size !== 50) q.set("size", String(f.size));
    router.push(`/team?${q.toString()}`);
  }

  return (
    <div ref={topRef} className="flex flex-col gap-8">
      <div className="flex flex-col gap-5 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-6 shadow-sm">
        <div className="flex gap-2">
          <input
            type="search"
            value={f.q}
            onChange={(e) => update({ q: e.target.value })}
            placeholder="Tìm theo tiêu đề hoặc tag..."
            aria-label="Tìm task"
            className="flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="w-24 text-sm font-medium">Trạng thái:</span>
          <button type="button" onClick={() => goServer("all")} className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${CHIP_OFF}`}>
            Tất cả
          </button>
          <span className={`rounded-full px-3 py-1 text-xs font-medium ${CHIP_ON}`}>Đang mở</span>
          <button type="button" onClick={() => goServer("closed")} className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${CHIP_OFF}`}>
            Đã hoàn thành
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="w-24 text-sm font-medium">Thời gian tạo:</span>
          {SORTS.map((s) => (
            <button key={s.id} type="button" onClick={() => update({ sort: s.id })} aria-pressed={f.sort === s.id} className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${f.sort === s.id ? CHIP_ON : CHIP_OFF}`}>
              {s.label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="w-24 text-sm font-medium">Cập nhật lúc:</span>
          {TIME_PRESETS.map((p) => (
            <button key={p.id} type="button" onClick={() => update({ time: p.id, from: "", to: "" })} aria-pressed={f.time === p.id && !f.from && !f.to} className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${f.time === p.id && !f.from && !f.to ? CHIP_ON : CHIP_OFF}`}>
              {p.label}
            </button>
          ))}
          <div className="ml-2 flex items-center gap-2 border-l border-[var(--color-border)] pl-2">
            <input type="date" value={f.from} onChange={(e) => update({ from: e.target.value, time: "all" })} className={INPUT} title="Từ ngày" aria-label="Từ ngày" />
            <span className="text-xs text-[var(--color-ink-muted)]">-</span>
            <input type="date" value={f.to} onChange={(e) => update({ to: e.target.value, time: "all" })} className={INPUT} title="Đến ngày" aria-label="Đến ngày" />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="w-24 text-sm font-medium">Hiển thị:</span>
          {SIZES.map((n) => (
            <button key={n} type="button" onClick={() => update({ size: n })} aria-pressed={f.size === n} className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${f.size === n ? CHIP_ON : CHIP_OFF}`}>
              {n} / trang
            </button>
          ))}
        </div>

        {assignees.length > 0 && (
          <div className="flex items-start gap-2">
            <span className="w-24 pt-1 text-sm font-medium">Người làm:</span>
            <div className="flex flex-1 flex-wrap gap-2">
              <button type="button" onClick={() => update({ assignee: "" })} aria-pressed={!f.assignee} className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${!f.assignee ? CHIP_ON : CHIP_OFF}`}>
                Tất cả
              </button>
              {assignees.map((name) => (
                <button key={name} type="button" onClick={() => update({ assignee: name })} aria-pressed={f.assignee === name} className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${f.assignee === name ? CHIP_ON : CHIP_OFF}`}>
                  {name} ({assigneeCounts[name]})
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className={`transition-opacity ${stale ? "opacity-60" : ""}`} aria-busy={stale}>
        <p className="mb-3 text-sm text-[var(--color-ink-muted)]">
          Tổng cộng {total} task (Trang {page}/{totalPages})
        </p>
        {visible.length === 0 ? (
          <p className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-ink-muted)]">
            Không có task nào khớp với điều kiện lọc.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {visible.map((task) => (
              <TaskItem key={task.id} task={task} />
            ))}
          </ul>
        )}
      </div>

      {totalPages > 1 && (
        <nav aria-label="Phân trang" className="mt-4 flex items-center justify-between text-sm">
          <button type="button" disabled={page <= 1} onClick={() => goPage(page - 1)} className="rounded-md border border-[var(--color-border)] px-3 py-1.5 transition-colors hover:bg-[var(--color-surface-hover)] disabled:cursor-not-allowed disabled:opacity-40">
            Trang trước
          </button>
          <span className="text-[var(--color-ink-muted)]">Trang {page} / {totalPages}</span>
          <button type="button" disabled={page >= totalPages} onClick={() => goPage(page + 1)} className="rounded-md border border-[var(--color-border)] px-3 py-1.5 transition-colors hover:bg-[var(--color-surface-hover)] disabled:cursor-not-allowed disabled:opacity-40">
            Trang sau
          </button>
        </nav>
      )}
    </div>
  );
}
