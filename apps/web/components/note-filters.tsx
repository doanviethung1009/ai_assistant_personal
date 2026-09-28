import Link from "next/link";

import { NOTE_KINDS, NOTE_KIND_LABELS, type NoteKind } from "@/lib/types";

/**
 * Bộ lọc sổ tay.
 *
 * Là form GET thuần, không phải client component. Trạng thái lọc nằm trong
 * query string nên: trang vẫn là Server Component, lọc hoạt động cả khi
 * JavaScript chưa tải, và một bộ lọc cụ thể có thể bookmark hoặc gửi cho
 * người khác.
 */

const CONTROL_CLASS =
  "rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm";

export interface NoteFilterState {
  q: string;
  kind: NoteKind | "";
  pinned: boolean;
  sort: string;
}

const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: "updated_at", label: "Sửa gần nhất" },
  { value: "use_count", label: "Hay dùng nhất" },
  { value: "last_used_at", label: "Dùng gần nhất" },
  { value: "created_at", label: "Mới tạo" },
  { value: "title", label: "Tên A→Z" },
];

export function NoteFilters({
  state,
  counts,
  total,
}: {
  state: NoteFilterState;
  /** Số note theo từng loại, để hiện ngay trong ô chọn. */
  counts: Record<string, number>;
  total: number;
}) {
  const isFiltered =
    state.q !== "" || state.kind !== "" || state.pinned || state.sort !== "updated_at";

  return (
    <form
      method="get"
      className="flex flex-wrap items-end gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3"
      aria-label="Lọc sổ tay"
    >
      <div className="min-w-[200px] flex-1">
        <label
          htmlFor="note-search"
          className="mb-1 block text-xs font-medium text-[var(--color-ink-muted)]"
        >
          Tìm trong tiêu đề và nội dung
        </label>
        <input
          id="note-search"
          name="q"
          type="search"
          defaultValue={state.q}
          placeholder="pg_dump, deleted_at, COMPOSE_PROJECT_NAME…"
          className={`${CONTROL_CLASS} w-full`}
        />
      </div>

      <div>
        <label
          htmlFor="note-kind-filter"
          className="mb-1 block text-xs font-medium text-[var(--color-ink-muted)]"
        >
          Loại
        </label>
        <select
          id="note-kind-filter"
          name="kind"
          defaultValue={state.kind}
          className={CONTROL_CLASS}
        >
          <option value="">Tất cả ({total})</option>
          {NOTE_KINDS.map((kind) => (
            <option key={kind} value={kind}>
              {NOTE_KIND_LABELS[kind]} ({counts[kind] ?? 0})
            </option>
          ))}
        </select>
      </div>

      <div>
        <label
          htmlFor="note-sort"
          className="mb-1 block text-xs font-medium text-[var(--color-ink-muted)]"
        >
          Sắp xếp
        </label>
        <select
          id="note-sort"
          name="sort"
          defaultValue={state.sort}
          className={CONTROL_CLASS}
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <label className="flex items-center gap-2 py-2 text-sm">
        <input
          type="checkbox"
          name="pinned"
          value="1"
          defaultChecked={state.pinned}
          className="size-4"
        />
        Chỉ mục đã ghim
      </label>

      <button
        type="submit"
        className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white"
      >
        Lọc
      </button>

      {isFiltered ? (
        <Link
          href="/notes"
          className="rounded-md border border-[var(--color-border)] px-3 py-2 text-sm transition-colors hover:bg-[var(--color-surface-hover)]"
        >
          Bỏ lọc
        </Link>
      ) : null}
    </form>
  );
}
