import { authEnabled } from "@/lib/auth-config";
import Link from "next/link";

import { ForbiddenPanel } from "@/components/forbidden-panel";
import { loadDocAccess } from "@/components/doc-access";
import { isInfraDoc } from "@/lib/doc-access";

import { Markdown } from "@/components/markdown";
import { DOCS, findDoc, readDoc, stripFrontMatter } from "@/lib/docs";

export const dynamic = "force-dynamic";

interface SearchParams {
  doc?: string;
}

export default async function DocsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  // findDoc chỉ khớp trong danh sách cứng, giá trị lạ sẽ về mục đầu tiên
  const entry = findDoc(params.doc);
  const access = await loadDocAccess();
  if (access.error) return access.error;
  // Tài liệu hạ tầng: ẩn khỏi danh sách và không đọc file nếu thiếu system:read.
  const blocked = isInfraDoc(entry.slug) && !access.canInfra;
  const visibleDocs = access.canInfra ? DOCS : DOCS.filter((doc) => !isInfraDoc(doc.slug));
  const content = blocked ? null : await readDoc(entry);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Tài liệu</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Đọc trực tiếp file markdown trong repo, không phải bản chép lại. Sửa
          file là trang này đổi theo.
        </p>
      </div>

      {/* ── Chọn tài liệu ───────────────────────────────────────────── */}
      <nav aria-label="Chọn tài liệu" className="flex flex-col gap-8">
        {/* Mỗi nhóm là một <details>: chỉ nhóm chứa tài liệu đang xem được mở sẵn,
            để trang không là bức tường hơn 40 thẻ. Không cần JS nên chạy ở Server Component. */}
        {Array.from(new Set(visibleDocs.map((doc) => doc.category))).map((category) => {
          const categoryDocs = visibleDocs.filter((doc) => doc.category === category);
          const hasActive = categoryDocs.some((doc) => doc.slug === entry.slug);
          return (
            <details key={category} open={hasActive} className="group">
              <summary className="mb-3 flex cursor-pointer select-none items-center gap-2 text-sm font-semibold uppercase tracking-wider text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]">
                <span className="transition-transform group-open:rotate-90" aria-hidden="true">
                  ▸
                </span>
                {category}
                <span className="rounded-full bg-[var(--color-surface-raised)] px-2 py-0.5 text-xs font-medium normal-case tracking-normal">
                  {categoryDocs.length}
                </span>
              </summary>
              <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {categoryDocs.map((doc) => {
                  const isActive = doc.slug === entry.slug;
                  return (
                    <li key={doc.slug} className="h-full">
                      <Link
                        href={`/docs?doc=${doc.slug}`}
                        aria-current={isActive ? "page" : undefined}
                        className={`flex h-full flex-col rounded-lg border p-3 transition-all hover:-translate-y-0.5 hover:shadow-sm ${
                          isActive
                            ? "border-[var(--color-accent)] bg-[var(--color-accent)]/10 ring-1 ring-[var(--color-accent)]/20"
                            : "border-[var(--color-border)] bg-[var(--color-surface-raised)] hover:border-[var(--color-ink-muted)]/30"
                        }`}
                      >
                        <span className="block text-sm font-medium">{doc.title}</span>
                        <span className="mt-1 block text-xs leading-relaxed text-[var(--color-ink-muted)]">
                          {doc.description}
                        </span>
                        <code className="mt-auto block truncate pt-3 text-xs text-[var(--color-ink-muted)] opacity-60">
                          {doc.file.replace(/\\/g, "/")}
                        </code>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </details>
          );
        })}
      </nav>

      {/* ── Nội dung ────────────────────────────────────────────────── */}
      <article className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 sm:p-6">
        {content === null ? (
          <ForbiddenPanel />
        ) : content.markdown === null ? (
          <div
            role="alert"
            className="rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 p-3"
          >
            <p className="text-sm font-medium text-[var(--color-danger)]">
              Không đọc được {entry.title}
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

      <p className="text-xs text-[var(--color-ink-muted)]">
        Muốn xem tiến độ thay vì kiến trúc thì mở tab{" "}
        <Link href="/roadmap" className="text-[var(--color-accent)] underline">
          Lộ trình
        </Link>
        .
      </p>
    </div>
  );
}
