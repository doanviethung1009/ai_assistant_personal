/**
 * Tài liệu chứa thông tin hạ tầng (IP, cách SSH, runbook, cấu hình domain/OAuth). Ở chế độ api chỉ
 * người có `system:read` (admin) xem được; tài liệu thường chỉ cần phiên còn hiệu lực ở core.
 * Thuần (không "server-only") để test được. Thêm tài liệu hạ tầng mới ở lib/docs.ts thì thêm slug ở đây.
 */
// GIỮ DANH SÁCH NÀY ĐỒNG BỘ: thêm tài liệu/spec có IP, hostname, cách SSH, ufw, domain/OAuth vào
// lib/docs.ts thì thêm slug vào đây (nếu không, mọi người dùng đăng nhập đều đọc được).
export const INFRA_DOC_SLUGS: ReadonlySet<string> = new Set([
  "proxmox-operations",
  "vm-layout-recovery",
  "systems-inventory",
  "proxmox-access",
  "proxmox-templates",
  "proxmox-deploy",
  "spec-proxmox-deploy",
  "deploy",
  "deployment-strategies",
  "docker-architecture",
  "staging-domain-https",
  "google-oauth-setup",
  "status",
  "spec-auth-multiuser",
  "spec-auth-web-p2",
]);

export function isInfraDoc(slug: string | undefined): boolean {
  return slug !== undefined && INFRA_DOC_SLUGS.has(slug);
}
