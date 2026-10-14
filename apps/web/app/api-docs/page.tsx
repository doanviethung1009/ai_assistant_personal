import { authEnabled } from "@/lib/auth-config";
import { loadDocAccess } from "@/components/doc-access";
import { Markdown } from "@/components/markdown";
import { ApiTester } from "@/components/api-tester";
import { findDoc, readDoc, stripFrontMatter } from "@/lib/docs";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function ApiDocsPage() {
  // Đọc trực tiếp file API_REFERENCE.md đã tạo ban nãy
  const access = await loadDocAccess();
  if (access.error) return access.error;
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
          <ApiTester />
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
{/* Đường dẫn tuyệt đối trên server chỉ hiện ở chế độ cục bộ (api: không lộ cấu trúc thư mục). */}
            {!authEnabled() ? (
            <p className="mt-2 break-all text-xs text-[var(--color-ink-muted)]">
              Đã thử đọc: <code>{content.resolvedPath}</code>
            </p>
            ) : null}
          </div>
        ) : (
          <Markdown>{stripFrontMatter(content.markdown)}</Markdown>
        )}
      </article>
    </div>
  );
}
