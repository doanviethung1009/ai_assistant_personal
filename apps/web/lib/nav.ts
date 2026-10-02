/**
 * Cấu hình điều hướng.
 *
 * Chia hai cấp theo tần suất dùng, KHÔNG dùng dropdown. Với tám mục thì bắt
 * người dùng bấm mới thấy danh sách là ẩn thông tin mà chẳng đổi lại được gì.
 *
 *   primary   — việc làm hàng ngày, dùng liên tục
 *   secondary — tài liệu về chính dự án, dùng thỉnh thoảng
 *
 * Khi Phase 2 và 3 có trang thật thì thêm vào `primary`, vì chúng cũng là
 * việc làm hàng ngày. Nếu `primary` vượt khoảng sáu mục thì lúc đó mới nên
 * cân nhắc sidebar, chứ chưa cần bây giờ.
 *
 * Các giai đoạn chưa làm cố tình KHÔNG xuất hiện ở đây. Nav nên chỉ chứa thứ
 * bấm được; lộ trình đã có tab Lộ trình lo việc đó.
 */

export interface NavItem {
  href: string;
  label: string;
  /** Nhãn ngắn cho màn hình hẹp. Bỏ trống thì dùng `label`. */
  short?: string;
}

export const PRIMARY_NAV: NavItem[] = [
  { href: "/", label: "Hôm nay" },
  { href: "/tasks", label: "Tất cả task", short: "Task" },
  { href: "/team", label: "Team", short: "Team" },
  { href: "/projects", label: "Dự án" },
  { href: "/notes", label: "Sổ tay" },
  { href: "/tags", label: "Quản lý Tag", short: "Tags" },
  { href: "/history", label: "Lịch sử duyệt web", short: "Lịch sử" },
  { href: "/trash", label: "Thùng rác", short: "Rác" },
];

export const SECONDARY_NAV: NavItem[] = [
  { href: "/architecture", label: "Kiến trúc" },
  { href: "/roadmap", label: "Lộ trình" },
  { href: "/docs", label: "Tài liệu" },
  { href: "/api-docs", label: "API" },
  { href: "/docs/ai-logs", label: "AI Trace" },
  { href: "/system", label: "Hệ thống" },
  { href: "/data", label: "Dữ liệu" },
];

export function isItemActive(href: string, pathname: string): boolean {
  // "/" chỉ khớp chính xác, nếu không nó sẽ khớp mọi đường dẫn
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
