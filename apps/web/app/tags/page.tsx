import Link from "next/link";
import { redirect } from "next/navigation";
import { DISPLAY_TZ, IS_LOCAL, getTagRulesApi, getTagsStatsApi } from "@/lib/api";
import { canView } from "@/lib/auth-guard";
import { TagManager } from "@/components/tag-manager";
import { TagRuleList } from "@/components/tag-rule-list";
import { ApiErrorPanel } from "@/components/api-error";

export const dynamic = "force-dynamic";

const RULES_PAGE_SIZE = 50;

// Lưu ý (ngoài phạm vi T7): danh sách tag chính bên dưới TagManager vẫn tải hết một lần
// (hiện ~474 tag), chưa phân trang server-side như AGENTS.md 3.5 yêu cầu.
export default async function TagsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const raw = (await searchParams).rulesPage;
  // Trần 20_000 trang x 50 = offset 1_000_000, đúng trần core (le=1_000_000); vượt thì core trả 422.
  const requested = Math.min(
    20_000,
    Math.max(1, Number.parseInt((Array.isArray(raw) ? raw[0] : raw) ?? "", 10) || 1),
  );

  let view;
  try {
    const [tags, rules, canDelete] = await Promise.all([
      getTagsStatsApi(),
      getTagRulesApi(requested),
      canView("task:write_any_work"),
    ]);
    view = { tags, rules, canDelete };
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }
  const { tags, rules, canDelete } = view;

  // ?rulesPage= vượt số trang thật (gỡ bớt rule, hoặc gõ tay) thì về trang cuối.
  // redirect() ném lỗi điều hướng nên phải nằm NGOÀI try/catch ở trên.
  const totalPages = Math.max(1, Math.ceil(rules.total / RULES_PAGE_SIZE));
  if (requested > totalPages) redirect(rulesHref(totalPages));

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Quản lý Tag</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Đổi tên hoặc xoá hàng loạt tag trên toàn bộ hệ thống (task và sổ tay).
        </p>
      </div>

      <TagManager initialTags={tags} />

      {IS_LOCAL ? null : (
        <section className="flex flex-col gap-3" aria-labelledby="tag-rules-heading">
          <div>
            <h2 id="tag-rules-heading" className="text-lg font-semibold tracking-tight">
              Quy tắc đồng bộ
            </h2>
            <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
              Tag đã đổi tên hoặc xoá trên task công việc được ghi nhớ, để Jira/Excel đồng bộ không đưa tag cũ
              trở lại. {canDelete ? "" : "Chỉ lead/admin gỡ được quy tắc."}
            </p>
          </div>
          <TagRuleList rules={rules.items} canDelete={canDelete} tz={DISPLAY_TZ} />
          {totalPages > 1 ? (
            <nav aria-label="Phân trang quy tắc" className="flex items-center justify-between text-sm">
              <PageLink href={rulesHref(requested - 1)} disabled={requested <= 1} label="Trang trước" />
              <span className="text-[var(--color-ink-muted)]">
                Trang {requested} / {totalPages} · Tổng: {rules.total} quy tắc
              </span>
              <PageLink href={rulesHref(requested + 1)} disabled={requested >= totalPages} label="Trang sau" />
            </nav>
          ) : (
            <p className="text-xs text-[var(--color-ink-muted)]">Tổng: {rules.total} quy tắc</p>
          )}
        </section>
      )}
    </div>
  );
}

function rulesHref(page: number): string {
  return page > 1 ? `/tags?rulesPage=${page}` : "/tags";
}

function PageLink({ href, disabled, label }: { href: string; disabled: boolean; label: string }) {
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
