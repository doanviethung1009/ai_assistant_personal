import Link from "next/link";

import { ApiErrorPanel } from "@/components/api-error";
import { NoteFilters, type NoteFilterState } from "@/components/note-filters";
import { NoteForm } from "@/components/note-form";
import { NoteItem } from "@/components/note-item";
import { IS_LOCAL, getNoteStats, listNotes, listProjects } from "@/lib/api";
import { NOTE_KINDS, type Note, type NoteKind, type NoteSortField } from "@/lib/types";

export const dynamic = "force-dynamic";

const PAGE_SIZE = 50;

const SORT_FIELDS: NoteSortField[] = [
  "updated_at",
  "created_at",
  "title",
  "use_count",
  "last_used_at",
];

/** Lấy một giá trị đơn từ searchParams, bỏ qua trường hợp mảng. */
function single(value: string | string[] | undefined): string {
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

/**
 * Dựng URL /notes giữ nguyên bộ lọc và tab. Dùng chung cho tab, phân trang và
 * link gợi ý để mọi chỗ đều không đánh rơi tham số nào.
 */
function notesHref(
  filters: NoteFilterState,
  overrides: { archived?: boolean; page?: number } = {},
): string {
  const archived = overrides.archived ?? filters.archived;
  const query = new URLSearchParams();
  if (filters.q) query.set("q", filters.q);
  if (filters.kind) query.set("kind", filters.kind);
  if (filters.pinned) query.set("pinned", "1");
  if (filters.sort !== "updated_at") query.set("sort", filters.sort);
  if (archived) query.set("archived", "1");
  if (overrides.page && overrides.page > 1) {
    query.set("page", String(overrides.page));
  }
  const qs = query.toString();
  return qs ? `/notes?${qs}` : "/notes";
}

function sumCounts(counts: Record<string, number>): number {
  return Object.values(counts).reduce((sum, value) => sum + value, 0);
}

function parseFilters(
  params: Record<string, string | string[] | undefined>,
): NoteFilterState {
  const rawKind = single(params.kind);
  const rawSort = single(params.sort);

  return {
    q: single(params.q).slice(0, 200),
    // Chỉ nhận giá trị nằm trong enum. Query string là dữ liệu không đáng tin,
    // nếu đưa thẳng xuống API thì backend sẽ trả 422 thay vì hiện trang trống.
    kind: (NOTE_KINDS as string[]).includes(rawKind) ? (rawKind as NoteKind) : "",
    pinned: single(params.pinned) === "1",
    sort: (SORT_FIELDS as string[]).includes(rawSort) ? rawSort : "updated_at",
    // File/memory mode không có lưu trữ: ép về tab Đang dùng dù URL ghi gì.
    archived: !IS_LOCAL && single(params.archived) === "1",
  };
}

export default async function NotesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const rawParams = await searchParams;
  const filters = parseFilters(rawParams);
  // Trần 10_000 trang: số quá lớn làm offset vượt int64 của Postgres và backend trả 500.
  const currentPage = Math.min(
    10_000,
    Math.max(1, Number.parseInt(single(rawParams.page), 10) || 1),
  );
  const archiveSupported = !IS_LOCAL;

  let notes: Note[];
  let total: number;
  let counts: Record<string, number>;
  let activeTotal: number;
  let archivedTotal: number;
  let archivedMatches = 0;
  let projects: { id: string; key: string; name: string }[];

  try {
    const listOptions = {
      kind: filters.kind ? [filters.kind] : undefined,
      query: filters.q || undefined,
      pinnedOnly: filters.pinned,
      sortBy: filters.sort as NoteSortField,
      // title sắp xếp tăng dần mới tự nhiên, các field thời gian thì giảm dần
      sortDesc: filters.sort !== "title",
    };
    // Số trên hai tab luôn lấy từ stats của từng view, bất kể đang xem tab nào.
    const [page, activeStats, archivedStats, projectList, hint] =
      await Promise.all([
        listNotes({
          ...listOptions,
          archived: filters.archived,
          limit: PAGE_SIZE,
          offset: (currentPage - 1) * PAGE_SIZE,
        }),
        getNoteStats({ archived: false }),
        archiveSupported ? getNoteStats({ archived: true }) : Promise.resolve({}),
        listProjects(true),
        // Gợi ý "khớp trong Lưu trữ": rủi ro UX chính là tìm không ra note cũ
        // vì đã lưu trữ. Chỉ tốn thêm request khi đang tìm ở tab Đang dùng.
        archiveSupported && !filters.archived && filters.q
          ? listNotes({ ...listOptions, archived: true, limit: 1 })
          : Promise.resolve(null),
      ]);
    notes = page.items;
    total = page.total;
    counts = filters.archived ? archivedStats : activeStats;
    activeTotal = sumCounts(activeStats);
    archivedTotal = sumCounts(archivedStats);
    archivedMatches = hint?.total ?? 0;
    projects = projectList;
  } catch (error) {
    return (
      <ApiErrorPanel
        message={error instanceof Error ? error.message : String(error)}
      />
    );
  }

  const totalAll = sumCounts(counts);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const isFiltered = filters.q !== "" || filters.kind !== "" || filters.pinned;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Sổ tay</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Chỗ dán lại câu lệnh, câu SQL và đoạn cấu hình đã mất công tìm ra, để
          lần sau copy chứ không phải dò lại.
        </p>
      </div>

      <NoteForm projects={projects} />

      {archiveSupported ? (
        <nav aria-label="Chế độ xem sổ tay" className="flex gap-2 text-sm">
          <TabLink
            href={notesHref(filters, { archived: false })}
            active={!filters.archived}
            label={`Đang dùng (${activeTotal})`}
          />
          <TabLink
            href={notesHref(filters, { archived: true })}
            active={filters.archived}
            label={`Lưu trữ (${archivedTotal})`}
          />
        </nav>
      ) : null}

      <NoteFilters state={filters} counts={counts} total={totalAll} />

      {archivedMatches > 0 ? (
        <p className="text-sm text-[var(--color-ink-muted)]">
          Có {archivedMatches} mục khớp trong Lưu trữ.{" "}
          <Link
            href={notesHref(filters, { archived: true })}
            className="underline"
          >
            Xem
          </Link>
        </p>
      ) : null}

      <p className="text-sm text-[var(--color-ink-muted)]">
        {total === 0
          ? isFiltered
            ? "Không có mục nào khớp bộ lọc"
            : filters.archived
              ? "Chưa có mục nào được lưu trữ"
              : "Sổ tay đang trống"
          : `${total} mục${isFiltered ? " khớp bộ lọc" : ""}`}
      </p>

      {notes.length === 0 ? (
        <p className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-ink-muted)]">
          {isFiltered
            ? "Thử bỏ bớt điều kiện lọc, hoặc tìm bằng một đoạn ngắn hơn."
            : "Mở phần Thêm vào sổ tay ở trên để lưu mục đầu tiên."}
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {notes.map((note) => (
            <NoteItem
              key={note.id}
              note={note}
              archiveSupported={archiveSupported}
            />
          ))}
        </ul>
      )}

      {totalPages > 1 ? (
        <nav
          aria-label="Phân trang"
          className="flex items-center justify-between text-sm"
        >
          <PageLink
            href={notesHref(filters, { page: currentPage - 1 })}
            disabled={currentPage <= 1}
            label="Trang trước"
          />
          <span className="text-[var(--color-ink-muted)]">
            Trang {currentPage} / {totalPages} · Tổng: {total} kết quả
          </span>
          <PageLink
            href={notesHref(filters, { page: currentPage + 1 })}
            disabled={currentPage >= totalPages}
            label="Trang sau"
          />
        </nav>
      ) : null}

      <section className="rounded-lg border border-dashed border-[var(--color-border)] p-4">
        <h2 className="text-sm font-semibold">Về nội dung của sổ tay</h2>
        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Nội dung được lưu nguyên văn và chỉ dùng để copy. App không bao giờ tự
          chạy nó, kể cả với mục loại Câu lệnh hay SQL. Mục được đánh dấu
          <span className="mx-1 font-medium">cẩn thận</span>
          sẽ hỏi lại một lần trước khi copy.
        </p>
        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Sổ tay lưu văn bản thuần, <strong>không mã hoá</strong>. Đừng dán mật
          khẩu hay khoá API thật vào đây; thay bằng tên biến môi trường như{" "}
          <code>$POSTGRES_PASSWORD</code> rồi để giá trị thật trong{" "}
          <code>.env</code>.
        </p>
        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Xoá là xoá mềm: mục đã xoá nằm ở tab Thùng rác và còn phục hồi được.
        </p>
        {archiveSupported ? (
          <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
            Lưu trữ khác Thùng rác: mục lưu trữ chỉ bị ẩn khỏi danh sách hằng
            ngày, vẫn sửa và copy được, và không bao giờ tự bị xoá.
          </p>
        ) : null}
      </section>
    </div>
  );
}

/** Tab chọn view Đang dùng / Lưu trữ; dùng Link để giữ trang là Server Component. */
function TabLink({
  href,
  active,
  label,
}: {
  href: string;
  active: boolean;
  label: string;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`rounded-md border px-3 py-1.5 transition-colors ${
        active
          ? "border-[var(--color-accent)] bg-[var(--color-surface-raised)] font-medium"
          : "border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]"
      }`}
    >
      {label}
    </Link>
  );
}

function PageLink({
  href,
  disabled,
  label,
}: {
  href: string;
  disabled: boolean;
  label: string;
}) {
  if (disabled) {
    return (
      <span className="cursor-not-allowed rounded-md border border-[var(--color-border)] px-3 py-1.5 text-[var(--color-ink-muted)] opacity-40">
        {label}
      </span>
    );
  }
  return (
    <Link
      href={href}
      className="rounded-md border border-[var(--color-border)] px-3 py-1.5 transition-colors hover:bg-[var(--color-surface-hover)]"
    >
      {label}
    </Link>
  );
}
