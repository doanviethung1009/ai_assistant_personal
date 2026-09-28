import { ApiErrorPanel } from "@/components/api-error";
import { NoteFilters, type NoteFilterState } from "@/components/note-filters";
import { NoteForm } from "@/components/note-form";
import { NoteItem } from "@/components/note-item";
import { getNoteStats, listNotes, listProjects } from "@/lib/api";
import { NOTE_KINDS, type Note, type NoteKind, type NoteSortField } from "@/lib/types";

export const dynamic = "force-dynamic";

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
  };
}

export default async function NotesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const filters = parseFilters(await searchParams);

  let notes: Note[];
  let total: number;
  let counts: Record<string, number>;
  let projects: { id: string; key: string; name: string }[];

  try {
    const [page, stats, projectList] = await Promise.all([
      listNotes({
        kind: filters.kind ? [filters.kind] : undefined,
        query: filters.q || undefined,
        pinnedOnly: filters.pinned,
        sortBy: filters.sort as NoteSortField,
        // title sắp xếp tăng dần mới tự nhiên, các field thời gian thì giảm dần
        sortDesc: filters.sort !== "title",
        limit: 200,
      }),
      getNoteStats(),
      listProjects(true),
    ]);
    notes = page.items;
    total = page.total;
    counts = stats;
    projects = projectList;
  } catch (error) {
    return (
      <ApiErrorPanel
        message={error instanceof Error ? error.message : String(error)}
      />
    );
  }

  const totalAll = Object.values(counts).reduce((sum, value) => sum + value, 0);
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

      <NoteFilters state={filters} counts={counts} total={totalAll} />

      <p className="text-sm text-[var(--color-ink-muted)]">
        {total === 0
          ? isFiltered
            ? "Không có mục nào khớp bộ lọc"
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
            <NoteItem key={note.id} note={note} />
          ))}
        </ul>
      )}

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
      </section>
    </div>
  );
}
