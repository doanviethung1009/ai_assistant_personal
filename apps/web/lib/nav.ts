import {
  Sun,
  ListTodo,
  Users,
  FolderKanban,
  BookOpen,
  Shield,
  Tags,
  History,
  Trash2,
  Blocks,
  Map,
  FileText,
  Terminal,
  Sparkles,
  Settings,
  Database,
  Bot,
  BrainCircuit,
  type LucideIcon
} from "lucide-react";

/**
 * Cấu hình điều hướng.
 *
 * Đã chuyển sang giao diện Sidebar để hỗ trợ hiển thị nhiều mục hơn.
 */

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Nhãn ngắn cho màn hình hẹp. Bỏ trống thì dùng `label`. */
  short?: string;
}

export const PRIMARY_NAV: NavItem[] = [
  { href: "/", label: "Hôm nay", icon: Sun },
  { href: "/tasks", label: "Tất cả task", short: "Task", icon: ListTodo },
  { href: "/team", label: "Team", short: "Team", icon: Users },
  { href: "/projects", label: "Dự án", icon: FolderKanban },
  { href: "/notes", label: "Sổ tay", icon: BookOpen },
  { href: "/vault", label: "Két bảo mật", short: "Két", icon: Shield },
  { href: "/tags", label: "Quản lý Tag", short: "Tags", icon: Tags },
  { href: "/history", label: "Lịch sử duyệt web", short: "Lịch sử", icon: History },
  { href: "/trash", label: "Thùng rác", short: "Rác", icon: Trash2 },
];

export const SECONDARY_NAV: NavItem[] = [
  { href: "/architecture", label: "Kiến trúc", icon: Blocks },
  { href: "/roadmap", label: "Lộ trình", icon: Map },
  { href: "/docs", label: "Tài liệu", icon: FileText },
  { href: "/api-docs", label: "API", icon: Terminal },
  { href: "/system", label: "Hệ thống", icon: Settings },
  { href: "/data", label: "Dữ liệu", icon: Database },
];

export const AI_NAV: NavItem[] = [
  { href: "/ai-logs", label: "Nhật ký AI (Trace)", icon: Sparkles },
  { href: "/ai/ai-agent-guide", label: "Cẩm nang AI (Cursor/Copilot)", icon: BookOpen },
  { href: "/ai/new-agent-onboarding", label: "Nhập môn AI", icon: Shield },
  { href: "/ai/claude-operating-guide", label: "Claude Agent", icon: Bot },
  { href: "/ai/codex-operating-guide", label: "Codex Agent", icon: BrainCircuit },
];

export function isItemActive(href: string, pathname: string): boolean {
  // "/" chỉ khớp chính xác, nếu không nó sẽ khớp mọi đường dẫn
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}
