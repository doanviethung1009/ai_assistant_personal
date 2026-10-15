import { Suspense } from "react";

import { ApiOnlyNotice } from "@/components/admin/api-only-notice";
import { CreateUserDialog } from "@/components/admin/create-user-dialog";
import { PaginationBar } from "@/components/admin/pagination-bar";
import { TableSkeleton } from "@/components/admin/table-skeleton";
import { UserFiltersShell, type UserFilterValues } from "@/components/admin/user-filters";
import { UserTable } from "@/components/admin/user-table";
import { ApiErrorPanel } from "@/components/api-error";
import { ForbiddenPanel } from "@/components/forbidden-panel";
import { ADMIN_PAGE_SIZE, IS_LOCAL, getAssigneesApi, getMe, listAdminUsersApi } from "@/lib/api";
import { hasPermission } from "@/lib/permissions";
import { USER_ROLES } from "@/lib/types";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

const STATUSES = ["active", "invited", "disabled"];
const PROVIDERS = ["google", "local"];
/** offset ≤ 1e6 ở core: chặn page quá lớn thay vì để core trả 422. */
const MAX_PAGE = 20_000;

function one(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

/** Đọc `searchParams` thành bộ lọc đã làm sạch (giá trị lạ bị bỏ, không chuyển tiếp cho core). */
function parseFilters(sp: SearchParams): UserFilterValues & { page: number } {
  const role = one(sp.role);
  const status = one(sp.status);
  const provider = one(sp.auth_provider);
  const page = Number.parseInt(one(sp.page), 10);
  return {
    q: one(sp.q).trim().slice(0, 200),
    role: (USER_ROLES as readonly string[]).includes(role) ? role : "",
    status: STATUSES.includes(status) ? status : "",
    auth_provider: PROVIDERS.includes(provider) ? provider : "",
    locked: one(sp.locked) === "1",
    page: Number.isInteger(page) && page >= 1 ? Math.min(page, MAX_PAGE) : 1,
  };
}

function hrefFor(f: UserFilterValues, page: number): string {
  const params = new URLSearchParams();
  if (f.q) params.set("q", f.q);
  if (f.role) params.set("role", f.role);
  if (f.status) params.set("status", f.status);
  if (f.auth_provider) params.set("auth_provider", f.auth_provider);
  if (f.locked) params.set("locked", "1");
  if (page > 1) params.set("page", String(page));
  const qs = params.toString();
  return qs ? `/admin/users?${qs}` : "/admin/users";
}

/**
 * Quản trị người dùng. getMe dùng chung React.cache với layout (không thêm request); thiếu quyền thì
 * KHÔNG gọi /admin/*. Khung (tiêu đề, nút thêm, bộ lọc) hiện ngay, chỉ bảng nằm trong Suspense keyed
 * theo bộ lọc. Mỗi lần render: 1 GET /admin/users + 1 GET /tasks/assignees (cache uid:sv, chỉ khi có
 * team:read). Không có route admin nào qua cache dùng chung (UNCACHED_PREFIXES).
 */
export default async function AdminUsersPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  if (IS_LOCAL) return <ApiOnlyNotice title="Người dùng" />;

  let me;
  try {
    me = await getMe();
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }
  if (!hasPermission(me.permissions, "user:manage")) return <ForbiddenPanel />;

  const filters = parseFilters(await searchParams);
  const key = hrefFor(filters, filters.page);
  // Gợi ý alias dùng chung cho dialog tạo/mời và bảng; hỏng thì bỏ qua, không làm hỏng trang.
  const canSeeAssignees = hasPermission(me.permissions, "team:read");
  // KHÔNG await ở đây: promise chạy song song với listAdminUsersApi (Promise.all trong UsersData) và
  // dialog đọc nó bằng use() trong Suspense, nên shell không bị chặn và không nối tiếp getMe → assignees → list.
  const assignees: Promise<string[]> = canSeeAssignees
    ? getAssigneesApi().catch(() => [] as string[])
    : Promise.resolve([]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">Người dùng</h1>
        <CreateUserDialog assigneesPromise={assignees} />
      </div>
      <UserFiltersShell values={filters}>
        <Suspense key={key} fallback={<TableSkeleton />}>
          <UsersData filters={filters} meId={me.id} assignees={assignees} />
        </Suspense>
      </UserFiltersShell>
    </div>
  );
}

async function UsersData({
  filters,
  meId,
  assignees,
}: {
  filters: UserFilterValues & { page: number };
  meId: string;
  assignees: Promise<string[]>;
}) {
  let data;
  let assigneeList: string[];
  try {
    [data, assigneeList] = await Promise.all([
      listAdminUsersApi({
        q: filters.q || undefined,
        role: filters.role || undefined,
        status: filters.status || undefined,
        auth_provider: filters.auth_provider || undefined,
        locked: filters.locked,
        page: filters.page,
      }),
      assignees,
    ]);
  } catch (error) {
    return <ApiErrorPanel error={error} />;
  }

  return (
    <div className="space-y-4">
      <UserTable users={data.items} meId={meId} assignees={assigneeList} nowMs={Date.now()} />
      <PaginationBar
        page={filters.page}
        total={data.total}
        pageSize={ADMIN_PAGE_SIZE}
        hrefFor={(p) => hrefFor(filters, p)}
      />
    </div>
  );
}
