import { Markdown } from "@/components/markdown";
import { findDoc, readDoc, stripFrontMatter } from "@/lib/docs";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function ApiDocsPage() {
  // Đọc trực tiếp file API_REFERENCE.md đã tạo ban nãy
  const entry = findDoc("api-reference");
  const content = await readDoc(entry);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Tài liệu API Backend</h1>
          <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
            Tra cứu nhanh các endpoint, phương thức, và payload của hệ thống.
          </p>
        </div>
        <div className="flex gap-2">
          {/* Tuỳ chọn trỏ link tới Swagger UI nếu Backend đang chạy */}
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-[var(--color-accent-hover)]"
          >
            Mở Swagger UI (Nếu Backend đang chạy)
          </a>
        </div>
      </div>

      <article className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 sm:p-6">
        {content.markdown === null ? (
          <div
            role="alert"
            className="rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 p-3"
          >
            <p className="text-sm font-medium text-[var(--color-danger)]">
              Không đọc được tài liệu API
            </p>
            <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
              {content.error}
            </p>
            <p className="mt-2 break-all text-xs text-[var(--color-ink-muted)]">
              Đã thử đọc: <code>{content.resolvedPath}</code>
            </p>
          </div>
        ) : (
          <Markdown>{stripFrontMatter(content.markdown)}</Markdown>
        )}
      </article>
    </div>
  );
}
