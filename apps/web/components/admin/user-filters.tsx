"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import { USER_ROLES, USER_ROLE_LABELS, USER_STATUS_LABELS } from "@/lib/types";

export interface UserFilterValues {
  q: string;
  role: string;
  status: string;
  auth_provider: string;
  locked: boolean;
}

const SELECT =
  "rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]";

/**
 * Thanh lọc + vùng bảng. Bộ lọc ghi vào URL bằng router.replace trong startTransition (thấy được
 * ngay, bảng cũ mờ đi thay vì trắng trang) và luôn về page=1. Ô tìm kiếm debounce 300 ms để một lần
 * gõ chỉ tốn một lời gọi core. `children` là bảng do Server Component dựng (đã bọc Suspense keyed).
 */
export function UserFiltersShell({ values, children }: { values: UserFilterValues; children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [pending, startTransition] = useTransition();
  // Giữ bản sao cục bộ: giữa lúc bấm và lúc URL mới về, các ô không bật ngược về giá trị cũ.
  const [local, setLocal] = useState(values);
  const q = local.q;
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  function push(next: UserFilterValues) {
    setLocal(next);
    const params = new URLSearchParams();
    if (next.q.trim()) params.set("q", next.q.trim());
    if (next.role) params.set("role", next.role);
    if (next.status) params.set("status", next.status);
    if (next.auth_provider) params.set("auth_provider", next.auth_provider);
    if (next.locked) params.set("locked", "1");
    const qs = params.toString();
    startTransition(() => router.replace(qs ? `${pathname}?${qs}` : pathname));
  }

  function onQuery(value: string) {
    setLocal((prev) => ({ ...prev, q: value }));
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => push({ ...local, q: value }), 300);
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2" role="search" aria-busy={pending}>
        <input
          type="search"
          value={q}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="Tìm email, tên đăng nhập, tên..."
          maxLength={200}
          aria-label="Tìm người dùng"
          className="w-64 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
        />
        <select aria-label="Vai trò" value={local.role} onChange={(e) => push({ ...local, role: e.target.value })} className={SELECT}>
          <option value="">Mọi vai trò</option>
          {USER_ROLES.map((r) => (
            <option key={r} value={r}>
              {USER_ROLE_LABELS[r]}
            </option>
          ))}
        </select>
        <select aria-label="Trạng thái" value={local.status} onChange={(e) => push({ ...local, status: e.target.value })} className={SELECT}>
          <option value="">Mọi trạng thái</option>
          {(["active", "invited", "disabled"] as const).map((s) => (
            <option key={s} value={s}>
              {USER_STATUS_LABELS[s]}
            </option>
          ))}
        </select>
        <select aria-label="Loại tài khoản" value={local.auth_provider} onChange={(e) => push({ ...local, auth_provider: e.target.value })} className={SELECT}>
          <option value="">Google và nội bộ</option>
          <option value="google">Google</option>
          <option value="local">Nội bộ</option>
        </select>
        <label className="flex items-center gap-1.5 text-sm text-[var(--color-ink-muted)]">
          <input type="checkbox" checked={local.locked} onChange={(e) => push({ ...local, locked: e.target.checked })} />
          Đang khoá tạm
        </label>
        {pending ? <span className="text-xs text-[var(--color-ink-muted)]">Đang lọc...</span> : null}
      </div>
      <div className={`transition-opacity ${pending ? "opacity-50" : ""}`}>{children}</div>
    </>
  );
}
