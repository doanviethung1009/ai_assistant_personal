import Link from "next/link";
import { Suspense } from "react";

import { ApiOnlyNotice } from "@/components/admin/api-only-notice";
import { AuditTable } from "@/components/admin/audit-table";
import { PaginationBar } from "@/components/admin/pagination-bar";
import { TableSkeleton } from "@/components/admin/table-skeleton";
import { ApiErrorPanel } from "@/components/api-error";
import { ForbiddenPanel } from "@/components/forbidden-panel";
import { ADMIN_PAGE_SIZE, DISPLAY_TZ, IS_LOCAL, getMe, listAuditLogApi } from "@/lib/api";
import { zonedLocalToUtcIso } from "@/lib/format";
import { hasPermission } from "@/lib/permissions";
import { AUDIT_ACTIONS } from "@/lib/types";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const MAX_PAGE = 20_000;

interface AuditFilters {
  action: string;
  actor: string;
  target: string;
  since: string;
  until: string;
  page: number;
}

function one(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

/** Giá trị lạ (không phải UUID/ngày/action đã biết) bị bỏ thay vì chuyển cho core. */
function parseFilters(sp: SearchParams): AuditFilters {
  const action = one(sp.action);
  const actor = one(sp.actor);
  const target = one(sp.target);
  const since = one(sp.since);
  const until = one(sp.until);
  const page = Number.parseInt(one(sp.page), 10);
  return {
    action: (AUDIT_ACTIONS as readonly string[]).includes(action) ? action : "",
    actor: UUID_RE.test(actor) ? actor : "",
    target: UUID_RE.test(target) ? target : "",
    since: DATE_RE.test(since) ? since : "",
    until: DATE_RE.test(until) ? until : "",
    page: Number.isInteger(page) && page >= 1 ? Math.min(page, MAX_PAGE) : 1,
  };
}

function hrefFor(f: AuditFilters, page: number): string {
  const params = new URLSearchParams();
  if (f.action) params.set("action", f.action);
  if (f.actor) params.set("actor", f.actor);
  if (f.target) params.set("target", f.target);
  if (f.since) params.set("since", f.since);
  if (f.until) params.set("until", f.until);
  if (page > 1) params.set("page", String(page));
  const qs = params.toString();
  return qs ? `/admin/audit?${qs}` : "/admin/audit";
}

const FIELD =
  "rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]";

/**
 * Nhật ký kiểm toán (chỉ đọc). Bộ lọc là form GET thuần (không JS) ghi vào URL; phân trang
 * `?page=` 50/trang giữ mọi bộ lọc. Khoảng ngày hiểu theo múi giờ hiển thị của server.
 */
export default async function AdminAuditPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  if (IS_LOCAL) return <ApiOnlyNotice title="Nhật ký" />;

  try {
    const me = await getMe();
    if (!hasPermission(me.permissions, "user:manage")) return <ForbiddenPanel />;
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }

  const filters = parseFilters(await searchParams);

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold tracking-tight">Nhật ký</h1>
      <form method="get" action="/admin/audit" className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-[var(--color-ink-muted)]">
          Hành động
          <select name="action" defaultValue={filters.action} className={`${FIELD} mt-1 block`}>
            <option value="">Tất cả</option>
            {AUDIT_ACTIONS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-[var(--color-ink-muted)]">
          Người thực hiện (id)
          <input name="actor" defaultValue={filters.actor} maxLength={36} className={`${FIELD} mt-1 block w-72`} />
        </label>
        <label className="text-xs text-[var(--color-ink-muted)]">
          Đối tượng (id)
          <input name="target" defaultValue={filters.target} maxLength={36} className={`${FIELD} mt-1 block w-72`} />
        </label>
        <label className="text-xs text-[var(--color-ink-muted)]">
          Từ ngày
          <input name="since" type="date" defaultValue={filters.since} className={`${FIELD} mt-1 block`} />
        </label>
        <label className="text-xs text-[var(--color-ink-muted)]">
          Đến ngày
          <input name="until" type="date" defaultValue={filters.until} className={`${FIELD} mt-1 block`} />
        </label>
        <button type="submit" className="rounded-md bg-[var(--color-accent)] px-4 py-1.5 text-sm font-medium text-white">
          Lọc
        </button>
        <Link href="/admin/audit" className="px-2 py-1.5 text-sm text-[var(--color-ink-muted)] underline">
          Xoá lọc
        </Link>
      </form>

      <Suspense key={hrefFor(filters, filters.page)} fallback={<TableSkeleton />}>
        <AuditData filters={filters} />
      </Suspense>
    </div>
  );
}

async function AuditData({ filters }: { filters: AuditFilters }) {
  let data;
  try {
    data = await listAuditLogApi({
      action: filters.action || undefined,
      actor_user_id: filters.actor || undefined,
      target_id: filters.target || undefined,
      since: filters.since ? zonedLocalToUtcIso(`${filters.since}T00:00:00`, DISPLAY_TZ) || undefined : undefined,
      until: filters.until ? zonedLocalToUtcIso(`${filters.until}T23:59:59`, DISPLAY_TZ) || undefined : undefined,
      page: filters.page,
    });
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }
  return (
    <div className="space-y-4">
      <AuditTable entries={data.items} tz={DISPLAY_TZ} />
      <PaginationBar page={filters.page} total={data.total} pageSize={ADMIN_PAGE_SIZE} hrefFor={(p) => hrefFor(filters, p)} />
    </div>
  );
}
