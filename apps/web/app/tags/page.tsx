import { getTagsStatsApi } from "@/lib/api";
import { TagManager } from "@/components/tag-manager";
import { ApiErrorPanel } from "@/components/api-error";

export const dynamic = "force-dynamic";

export default async function TagsPage() {
  try {
    const tags = await getTagsStatsApi();

    return (
      <div className="flex flex-col gap-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Quản lý Tag</h1>
          <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
            Đổi tên hoặc xoá hàng loạt tag trên toàn bộ hệ thống (task và sổ tay).
          </p>
        </div>

        <TagManager initialTags={tags} />
      </div>
    );
  } catch (error) {
    return <ApiErrorPanel message={error instanceof Error ? error.message : String(error)} />;
  }
}
