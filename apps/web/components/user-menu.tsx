import Link from "next/link";

import { logoutAction } from "@/app/login/actions";
import type { MeRead } from "@/lib/types";

/**
 * Khối người dùng ở cuối sidebar. `name` do Google cấp (không tin cậy) nên chỉ render bằng text
 * node và cắt độ dài. Đăng xuất là form POST tới Server Action (không phải link GET).
 */
export function UserMenu({ me }: { me: MeRead }) {
  const label = (me.name || me.email).slice(0, 80);
  const initial = Array.from(label)[0]?.toUpperCase() ?? "?";
  return (
    <div className="flex items-center gap-3 border-t border-[var(--color-border)] px-4 py-3">
      <span
        aria-hidden
        className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[var(--color-accent)]/15 text-sm font-semibold text-[var(--color-accent)]"
      >
        {initial}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-[var(--color-ink)]" title={label}>
          {label}
        </p>
        <p className="text-xs text-[var(--color-ink-muted)]">
          {me.role} ·{" "}
          <Link href="/me" className="underline hover:text-[var(--color-ink)]">
            Hồ sơ
          </Link>
        </p>
      </div>
      <form action={logoutAction}>
        <button
          type="submit"
          className="rounded px-2 py-1 text-xs text-[var(--color-ink-muted)] transition hover:bg-black/10 hover:text-[var(--color-ink)]"
        >
          Đăng xuất
        </button>
      </form>
    </div>
  );
}

export function UserMenuSkeleton() {
  return (
    <div aria-hidden className="flex items-center gap-3 border-t border-[var(--color-border)] px-4 py-3">
      <span className="size-8 animate-pulse rounded-full bg-black/10" />
      <span className="h-4 w-28 animate-pulse rounded bg-black/10" />
    </div>
  );
}
