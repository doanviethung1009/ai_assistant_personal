/**
 * Định nghĩa lộ trình dự án.
 *
 * Đây là nguồn sự thật cho trang /roadmap. Khi hoàn thành một mục, sửa
 * `status` ở đây. Cố tình để dạng dữ liệu thay vì viết cứng trong JSX để
 * trang chỉ lo phần hiển thị.
 *
 * Quy ước status:
 *   done     đã làm và đã chạy được
 *   partial  đã viết code nhưng chưa verify hết
 *   doing    đang làm
 *   planned  chưa bắt đầu
 */

export type ItemStatus = "done" | "partial" | "doing" | "planned";

export interface FlowItem {
  label: string;
  status: ItemStatus;
  note?: string;
}

export interface Phase {
  id: number;
  key: string;
  title: string;
  goal: string;
  status: ItemStatus;
  /** Thay đổi về kiến trúc mà phase này kéo theo. */
  architecture: string;
  items: FlowItem[];
}

export const STATUS_LABELS: Record<ItemStatus, string> = {
  done: "Xong",
  partial: "Chưa verify",
  doing: "Đang làm",
  planned: "Chưa làm",
};

export const PHASES: Phase[] = [
  {
    id: 1,
    key: "task-store",
    title: "Task store cá nhân",
    goal: "Nhập và theo dõi công việc hàng ngày, không phụ thuộc nguồn ngoài.",
    status: "doing",
    architecture:
      "Nền móng: FastAPI + SQLAlchemy async + Postgres, Next.js App Router với Server Action.",
    items: [
      { label: "CRUD task, project", status: "done" },
      { label: "Agenda hôm nay: quá hạn, đang làm, đã xếp lịch, sắp đến hạn", status: "done" },
      { label: "Thống kê nhanh và ghi thời gian đã làm", status: "done" },
      { label: "Tag với index GIN, tìm kiếm, lọc, phân trang", status: "done" },
      {
        label: "Xoá mềm với thùng rác 30 ngày",
        status: "done",
        note: "Ràng buộc unique dùng partial index để sync lại không bị chặn",
      },
      {
        label: "Ba chế độ lưu trữ: file JSON, bộ nhớ, Postgres",
        status: "done",
        note: "Đổi bằng biến DATA_SOURCE, chữ ký hàm giữ nguyên",
      },
      { label: "Xuất và nhập JSON, CSV", status: "done" },
      {
        label: "Backend chạy thật trên Postgres",
        status: "partial",
        note: "Code đã xong và pass typecheck, nhưng chưa chạy được vì Docker chưa lên",
      },
      {
        label: "Initial migration của Alembic",
        status: "planned",
        note: "migrations/versions còn trống, bootstrap sẽ autogenerate",
      },
      { label: "Rate limiting và RBAC", status: "planned", note: "Cần trước khi mở cho team" },
    ],
  },
  {
    id: 2,
    key: "integration",
    title: "Kết nối nguồn ngoài",
    goal: "Gom task từ Jira, Calendar, Obsidian vào cùng một task store.",
    status: "planned",
    architecture:
      "Thêm mcp-servers/, scheduler poll định kỳ, Telegram bot làm giao diện di động.",
    items: [
      {
        label: "Chốt Jira Cloud hay Data Center",
        status: "planned",
        note: "Đang chặn cả phase. Auth và endpoint khác nhau hoàn toàn",
      },
      { label: "MCP server cho Jira", status: "planned" },
      { label: "MCP server cho Google Calendar", status: "planned" },
      { label: "Đọc Obsidian vault từ đĩa", status: "planned" },
      { label: "Scheduler poll mỗi 2-5 phút", status: "planned", note: "Polling vì hệ thống sau NAT" },
      { label: "Telegram bot: briefing sáng và approval", status: "planned" },
    ],
  },
  {
    id: 3,
    key: "healthcheck",
    title: "Healthcheck hệ thống",
    goal: "Biết hệ thống có đang sống và bất thường ở đâu, chỉ đọc.",
    status: "planned",
    architecture:
      "Agent query PromQL và đọc Alertmanager. Không tự lưu metrics. Thêm audit log.",
    items: [
      {
        label: "Prometheus, Grafana, blackbox, các exporter",
        status: "partial",
        note: "Cấu hình đã viết trong infra/monitoring, chưa chạy lần nào",
      },
      { label: "Endpoint /metrics của core API", status: "done", note: "Label theo route template" },
      { label: "Alert rule: probe fail, 5xx, p95, RAM, disk, Postgres", status: "partial" },
      { label: "Agent đọc PromQL và diễn giải", status: "planned" },
      { label: "Audit log cho mọi tool call của agent", status: "planned" },
    ],
  },
  {
    id: 4,
    key: "deploy",
    title: "Hỗ trợ deploy",
    goal: "Trigger pipeline và đọc kết quả, giữ nguyên quyền quyết định của người.",
    status: "planned",
    architecture:
      "Approval gate qua Telegram inline button. Agent không có standing write access vào production.",
    items: [
      { label: "Mô hình system landscape và environment", status: "planned" },
      { label: "Trigger pipeline sẵn có, không tự viết deploy script", status: "planned" },
      { label: "Approval của người trước mỗi lần chạm production", status: "planned" },
      { label: "Đọc log và tóm tắt kết quả deploy", status: "planned" },
    ],
  },
  {
    id: 5,
    key: "tuning",
    title: "Tư vấn tuning",
    goal: "Đề xuất thay đổi kèm bằng chứng từ metrics, không tự apply.",
    status: "planned",
    architecture:
      "Cache snapshot metrics để so sánh trước và sau. Chỉ xuất recommendation kèm diff.",
    items: [
      { label: "Phân tích query chậm và index thiếu", status: "planned" },
      { label: "Đề xuất tài nguyên container", status: "planned" },
      { label: "So sánh trước và sau khi đổi", status: "planned" },
    ],
  },
];

/** Nền tảng dùng chung, không thuộc phase nào. */
export const FOUNDATION: FlowItem[] = [
  { label: "Docker Compose ba profile: core, llm, monitoring", status: "partial", note: "Chưa build lần nào" },
  { label: "Makefile gói toàn bộ lệnh vận hành", status: "done" },
  { label: "scripts/bootstrap.sh dựng từ đầu trên Ubuntu", status: "partial" },
  { label: "scripts/smoke-test.sh kiểm tra end-to-end qua HTTP", status: "partial" },
  { label: "LiteLLM gateway đa provider kèm budget cứng", status: "planned", note: "Cần API key thật" },
  { label: "Steering file cho Kiro: project, ops, status", status: "done" },
];

export function countByStatus(items: FlowItem[]): Record<ItemStatus, number> {
  const result: Record<ItemStatus, number> = {
    done: 0,
    partial: 0,
    doing: 0,
    planned: 0,
  };
  for (const item of items) result[item.status] += 1;
  return result;
}

/** Phần trăm hoàn thành, tính partial là nửa điểm. */
export function progressPercent(items: FlowItem[]): number {
  if (items.length === 0) return 0;
  const counts = countByStatus(items);
  const score = counts.done + counts.partial * 0.5 + counts.doing * 0.5;
  return Math.round((score / items.length) * 100);
}
