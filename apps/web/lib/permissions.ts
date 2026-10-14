/**
 * Quyền của core (apps/core/app/core/permissions.py), 9 giá trị. Web chỉ dùng để ẩn/hiện UI và chặn
 * sớm trong Server Action; core vẫn là bên quyết định thật. Thêm quyền ở core thì thêm ở đây:
 * tests/permissions.test.ts đọc file Python và báo lệch.
 * Thuần (không "server-only") để cả client component (nav) import được.
 */
export const PERMISSIONS = [
  "task:read_work",
  "task:write_any_work",
  "team:read",
  "integration:sync",
  "integration:manage",
  "project:write_any",
  "data:import",
  "user:manage",
  "system:read",
] as const;

export type Permission = (typeof PERMISSIONS)[number];

/** `"all"` là chế độ cục bộ (file/memory): không có đăng nhập nên mọi quyền đều mở. */
export type PermissionSet = readonly Permission[] | "all";

export function hasPermission(permissions: PermissionSet, permission: Permission): boolean {
  return permissions === "all" || permissions.includes(permission);
}
