import { ApiErrorPanel } from "@/components/api-error";
import { DISPLAY_TZ, IS_LOCAL, getMe } from "@/lib/api";
import type { MeRead } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Hồ sơ của người đang đăng nhập, CHỈ ĐỌC. Múi giờ là múi giờ server (DISPLAY_TZ), không có ô chọn;
 * alias Jira do quản trị viên đặt ở core. Tên/email là claim Google (không tin cậy): chỉ render text.
 */
export default async function MePage() {
  if (IS_LOCAL) {
    return (
      <div className="max-w-xl">
        <h1 className="text-2xl font-bold tracking-tight">Hồ sơ</h1>
        <p className="mt-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-2 text-sm text-[var(--color-ink-muted)]">
          Chế độ file/memory không có đăng nhập nên không có hồ sơ người dùng.
        </p>
      </div>
    );
  }

  let me: MeRead;
  try {
    me = await getMe();
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }

  const rows: [string, string][] = [
    ["Email", me.email],
    ["Tên", me.name ?? "(chưa có)"],
    ["Vai trò", me.role],
    ["Múi giờ (của server)", DISPLAY_TZ],
  ];

  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-bold tracking-tight">Hồ sơ</h1>
      <dl className="mt-5 divide-y divide-[var(--color-border)] rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)]">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4 px-4 py-3 text-sm">
            <dt className="text-[var(--color-ink-muted)]">{label}</dt>
            <dd className="min-w-0 break-words text-right font-medium">{value.slice(0, 200)}</dd>
          </div>
        ))}
        <div className="px-4 py-3 text-sm">
          <dt className="text-[var(--color-ink-muted)]">Alias Jira (quản trị viên đặt)</dt>
          <dd className="mt-2 flex flex-wrap gap-2">
            {me.aliases.length === 0 ? (
              <span className="text-[var(--color-ink-muted)]">Chưa có</span>
            ) : (
              me.aliases.map((a) => (
                <span key={`${a.source}:${a.alias}`} className="rounded-full bg-orange-500/10 px-2.5 py-0.5 text-xs font-bold text-orange-600 dark:text-orange-400">
                  {a.source}: {a.alias.slice(0, 100)}
                </span>
              ))
            )}
          </dd>
        </div>
        <div className="px-4 py-3 text-sm">
          <dt className="text-[var(--color-ink-muted)]">Quyền</dt>
          <dd className="mt-2 flex flex-wrap gap-2">
            {me.permissions.map((p) => (
              <code key={p} className="rounded bg-black/20 px-1.5 py-0.5 text-xs">
                {p}
              </code>
            ))}
          </dd>
        </div>
      </dl>
    </div>
  );
}
