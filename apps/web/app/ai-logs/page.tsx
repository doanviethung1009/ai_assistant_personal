import { listAiLogs } from "@/lib/api";
import { ContentViewer } from "@/components/content-viewer";

export const dynamic = "force-dynamic";

export default async function AiLogsPage() {
  let logs: any[] = [];
  let error = null;

  try {
    logs = await listAiLogs();
    // Sắp xếp mới nhất lên đầu
    logs.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  } catch (err) {
    error = err instanceof Error ? err.message : String(err);
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">AI Trace (Nhật ký tự động)</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Lưu vết toàn bộ quá trình Agent xử lý công việc từ file cấu trúc JSON/Database.
        </p>
      </div>

      {error ? (
        <div
          role="alert"
          className="rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 p-3"
        >
          <p className="text-sm font-medium text-[var(--color-danger)]">
            Không thể tải dữ liệu lịch sử
          </p>
          <p className="mt-1 text-sm text-[var(--color-ink-muted)]">{error}</p>
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {logs.length === 0 ? (
            <p className="text-sm text-[var(--color-ink-muted)]">Chưa có nhật ký nào.</p>
          ) : (
            logs.map((log) => (
              <article
                key={log.id}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 sm:p-6"
              >
                <div className="mb-3 flex items-center justify-between border-b border-[var(--color-border)] pb-3">
                  <span className="inline-flex items-center rounded-md bg-[var(--color-accent)]/10 px-2 py-1 text-xs font-medium text-[var(--color-accent)] ring-1 ring-inset ring-[var(--color-accent)]/20">
                    {log.category}
                  </span>
                  <time className="text-xs text-[var(--color-ink-muted)]">
                    {new Date(log.created_at).toLocaleString("vi-VN")}
                  </time>
                </div>
                
                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-[var(--color-ink)]">Prompt:</h3>
                  <ContentViewer content={log.prompt} title="Chi tiết Prompt" />
                </div>

                <div>
                  <h3 className="text-sm font-semibold text-[var(--color-ink)] mb-2">Phản hồi & Xử lý:</h3>
                  <ContentViewer content={log.response} title="Chi tiết Phản hồi (Markdown)" isMarkdown={true} />
                </div>
              </article>
            ))
          )}
        </div>
      )}
    </div>
  );
}
