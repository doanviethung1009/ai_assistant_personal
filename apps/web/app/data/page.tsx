import { ApiErrorPanel } from "@/components/api-error";
import { DataImport } from "@/components/data-import";
import { UrlSyncManager } from "@/components/url-sync-manager";
import { FileUploadManager } from "@/components/file-upload-manager";
import { ChromeHistoryManager } from "@/components/chrome-history-manager";
import { WipeDataManager } from "@/components/wipe-data-manager";
import { RestoreJsonManager } from "@/components/restore-json-manager";
import { getSyncUrlsApi } from "@/lib/api";
import {
  DATA_SOURCE,
  IS_LOCAL,
  listNotes,
  listProjects,
  listTasks,
} from "@/lib/api";
import { dataFilePath } from "@/lib/store/json-file";

export const dynamic = "force-dynamic";

const SOURCE_INFO: Record<
  string,
  { label: string; detail: string; tone: "ok" | "warn" }
> = {
  api: {
    label: "Core API và Postgres",
    detail:
      "Dữ liệu nằm trong Postgres, do apps/core quản lý. Đây là chế độ thật.",
    tone: "ok",
  },
  file: {
    label: "File JSON trên đĩa",
    detail:
      "Ghi nguyên tử qua file tạm rồi rename, giữ thêm một bản .bak của lần ghi trước.",
    tone: "ok",
  },
  memory: {
    label: "Bộ nhớ tạm",
    detail:
      "Dữ liệu mất khi dev server khởi động lại. Chuyển sang DATA_SOURCE=file nếu muốn giữ.",
    tone: "warn",
  },
};

const EXPORTS = [
  {
    href: "/api/export?format=json",
    title: "JSON đầy đủ",
    note: "Giữ nguyên tags và nhật ký thay đổi. Dùng để backup và để nạp lên Postgres sau này.",
  },
  {
    href: "/api/export?format=csv&entity=tasks",
    title: "CSV task",
    note: "Mở được bằng Excel. Tags nối bằng dấu chấm phẩy, không có nhật ký.",
  },
  {
    href: "/api/export?format=csv&entity=projects",
    title: "CSV project",
    note: "Danh sách project kèm mã và màu.",
  },
  {
    href: "/api/export?format=csv&entity=notes",
    title: "CSV sổ tay",
    note: "Câu lệnh và SQL. Nội dung nhiều dòng được bọc trong dấu ngoặc kép theo RFC 4180.",
  },
];

export default async function DataPage() {
  const syncUrls = await getSyncUrlsApi();
  let taskCount: number;
  let projectCount: number;
  let noteCount: number;

  try {
    // limit=1 vì chỉ cần con số `total`, không cần bản ghi
    const [tasks, projects, notes] = await Promise.all([
      listTasks({ includeClosed: true, limit: 1 }),
      listProjects(true),
      listNotes({ limit: 1 }),
    ]);
    taskCount = tasks.total;
    projectCount = projects.length;
    noteCount = notes.total;
  } catch (error) {
    return (
      <ApiErrorPanel
        message={error instanceof Error ? error.message : String(error)}
      />
    );
  }

  const info = SOURCE_INFO[DATA_SOURCE] ?? SOURCE_INFO.api!;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Dữ liệu</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Xuất ra JSON hoặc CSV để backup, nhập lại để phục hồi hoặc chuyển
          sang máy khác.
        </p>
      </div>

      <section
        className={`rounded-lg border p-4 ${info.tone === "warn"
          ? "border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10"
          : "border-[var(--color-border)] bg-[var(--color-surface-raised)]"
          }`}
      >
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold">
            Nguồn dữ liệu: {info.label}
          </h2>
          <code className="rounded bg-black/30 px-1.5 py-0.5 text-xs">
            DATA_SOURCE={DATA_SOURCE}
          </code>
        </div>

        <p className="mt-1 text-xs text-[var(--color-ink-muted)]">{info.detail}</p>

        {DATA_SOURCE === "file" ? (
          <p className="mt-2 break-all text-xs text-[var(--color-ink-muted)]">
            Đường dẫn file:{" "}
            <code className="rounded bg-black/30 px-1">{dataFilePath()}</code>
          </p>
        ) : null}

        <dl className="mt-3 flex gap-6 text-sm">
          <div>
            <dt className="text-xs text-[var(--color-ink-muted)]">Task</dt>
            <dd className="font-semibold tabular-nums">{taskCount}</dd>
          </div>
          <div>
            <dt className="text-xs text-[var(--color-ink-muted)]">Project</dt>
            <dd className="font-semibold tabular-nums">{projectCount}</dd>
          </div>
          <div>
            <dt className="text-xs text-[var(--color-ink-muted)]">Sổ tay</dt>
            <dd className="font-semibold tabular-nums">{noteCount}</dd>
          </div>
        </dl>
      </section>

      <section className="rounded-lg border border-dashed border-[var(--color-border)] p-4">
        <h2 className="text-sm font-semibold">Đổi nguồn dữ liệu</h2>
        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Không có nút bấm trên web — đổi <code>DATA_SOURCE</code> cần
          Next.js khởi động lại để đọc biến môi trường mới, một Server Action
          không làm được việc đó. Cách đổi khác nhau theo <strong>cách bạn
            đang chạy app</strong>, chọn đúng mục dưới đây:
        </p>

        <div className="mt-3 rounded-md border border-[var(--color-border)] bg-black/20 p-3">
          <p className="text-xs font-semibold text-[var(--color-ink)]">
            Đang chạy qua Docker (<code>make up</code>, có container{" "}
            <code>builder-web</code>)
          </p>
          <dl className="mt-2 flex flex-col gap-2 text-xs">
            <div className="flex flex-wrap items-baseline gap-2">
              <dt className="text-[var(--color-ink-muted)]">Chuyển sang Postgres (thật):</dt>
              <dd>
                <code className="rounded bg-black/30 px-1.5 py-0.5">make use-db</code>
              </dd>
            </div>
            <div className="flex flex-wrap items-baseline gap-2">
              <dt className="text-[var(--color-ink-muted)]">Chuyển sang file JSON (demo):</dt>
              <dd>
                <code className="rounded bg-black/30 px-1.5 py-0.5">make use-local</code>
              </dd>
            </div>
          </dl>
          <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
            Hai lệnh này sửa <code>.env</code> ở gốc repo rồi tự{" "}
            <code>docker compose up -d web</code> — chỉ sửa <code>.env</code>{" "}
            tay mà không chạy lại container thì web vẫn dùng giá trị cũ.
          </p>
        </div>

        <div className="mt-3 rounded-md border border-[var(--color-border)] bg-black/20 p-3">
          <p className="text-xs font-semibold text-[var(--color-ink)]">
            Đang chạy trực tiếp bằng <code>npm run dev</code> (không Docker,
            không database)
          </p>
          <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
            Sửa biến <code>DATA_SOURCE</code> trong{" "}
            <code>apps/web/.env.local</code> (file này chỉ web app trực tiếp
            đọc — Docker Compose truyền env riêng, không đọc file này), rồi
            dừng và chạy lại <code>npm run dev</code> để Next.js nạp giá trị
            mới. Next.js dev server không tự nạp lại biến môi trường khi file{" "}
            <code>.env.local</code> thay đổi, phải restart tay.
          </p>
          <pre className="mt-2 overflow-x-auto rounded-md border border-[var(--color-border)] bg-black/30 p-2 text-xs">
            <code>{`# apps/web/.env.local
DATA_SOURCE=file   # hoặc memory, hoặc api`}</code>
          </pre>
          <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
            Dùng <code>api</code> ở đây (gọi core API) thì cũng cần
            <code> CORE_API_URL</code> và <code>CORE_API_KEY</code> điền đúng
            trong cùng file — xem mẫu đầy đủ có sẵn trong{" "}
            <code>apps/web/.env.local</code> khi mới clone repo.
          </p>
        </div>

        <p className="mt-3 text-xs text-[var(--color-ink-muted)]">
          Hai nguồn <strong>không tự đồng bộ</strong> — dữ liệu nhập ở chế độ
          này không tự xuất hiện ở chế độ khác. Dùng JSON ở mục Xuất dữ liệu
          bên dưới để chuyển tay giữa hai nguồn.
        </p>
      </section>

      <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4">
        <h2 className="text-sm font-semibold">Xuất dữ liệu</h2>
        <ul className="mt-3 flex flex-col gap-2">
          {EXPORTS.map((item) => (
            <li
              key={item.href}
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-[var(--color-border)] px-3 py-2"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium">{item.title}</p>
                <p className="text-xs text-[var(--color-ink-muted)]">
                  {item.note}
                </p>
              </div>
              <a
                href={item.href}
                download
                className="shrink-0 rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm transition-colors hover:bg-[var(--color-surface-hover)]"
              >
                Tải về
              </a>
            </li>
          ))}
        </ul>
      </section>

      <DataImport allowReplace={IS_LOCAL} />

      <UrlSyncManager initialUrls={syncUrls} />
        <FileUploadManager />
        <ChromeHistoryManager />
        <RestoreJsonManager />
        <WipeDataManager />

      <section className="rounded-lg border border-dashed border-[var(--color-border)] p-4">
        <h2 className="text-sm font-semibold">Chuyển sang Postgres sau này</h2>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs text-[var(--color-ink-muted)]">
          <li>Ở chế độ file, tải bản JSON đầy đủ về máy.</li>
          <li>
            Dựng stack bằng <code>make bootstrap</code> để có Postgres và core
            API.
          </li>
          <li>
            Đổi <code>DATA_SOURCE=api</code> trong{" "}
            <code>apps/web/.env.local</code> và điền <code>CORE_API_KEY</code>.
          </li>
          <li>
            Quay lại trang này, nhập file JSON đó với chế độ{" "}
            <strong>Thêm vào</strong>.
          </li>
        </ol>
        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Không cần bộ chuyển đổi vì file JSON dùng đúng tên field như API.
          Project được đối chiếu theo <code>key</code> chứ không theo UUID, nên
          nhập từ máy khác vẫn khớp.
        </p>
      </section>
    </div>
  );
}
