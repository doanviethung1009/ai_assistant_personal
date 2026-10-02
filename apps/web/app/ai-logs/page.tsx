import { readFile } from "node:fs/promises";
import path from "node:path";
import { Markdown } from "@/components/markdown";

export const dynamic = "force-dynamic";

/** Thư mục gốc chứa tài liệu. Mặc định là gốc repo, tính từ apps/web. */
function docsDir(): string {
  return process.env.DOCS_DIR
    ? path.resolve(process.env.DOCS_DIR)
    : path.resolve(process.cwd(), "..", "..");
}

export default async function AiLogsPage() {
  const resolvedPath = path.join(docsDir(), "docs/ai_logs.md");
  let content = "";
  let error = null;

  try {
    content = await readFile(resolvedPath, "utf8");
  } catch (err) {
    error = err instanceof Error ? err.message : String(err);
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">AI Trace (Nhật ký tự động)</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Lưu vết toàn bộ quá trình Agent xử lý công việc để phục vụ truy vết và huấn luyện.
        </p>
      </div>

      <article className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 sm:p-6">
        {error ? (
          <div
            role="alert"
            className="rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 p-3"
          >
            <p className="text-sm font-medium text-[var(--color-danger)]">
              Không thể tải file lịch sử
            </p>
            <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
              {error}
            </p>
          </div>
        ) : (
          <Markdown>{content}</Markdown>
        )}
      </article>
    </div>
  );
}
