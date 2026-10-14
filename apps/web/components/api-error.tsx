import { redirect } from "next/navigation";

import { ForbiddenPanel } from "@/components/forbidden-panel";
import { classifyCoreError } from "@/lib/core-errors";

/**
 * Panel lỗi cho Server Component, đồng thời là nơi xử lý 401/403 theo bảng 3.4 của spec:
 *   no_session            → redirect /login
 *   token_invalid/inactive → redirect /auth/expired (xoá cookie rồi về /login)
 *   403 forbidden          → ForbiddenPanel
 *   401/403 không `code`   → lỗi cấu hình web→core, KHÔNG đăng xuất
 *   mạng/5xx               → panel lỗi chung, KHÔNG đăng xuất
 * Truyền `error` (lỗi bắt được) để phân loại; `message` chỉ cho chỗ không có error object.
 */
export function ApiErrorPanel({ error, message }: { error?: unknown; message?: string }) {
  const kind = classifyCoreError(error);
  if (kind === "unauthenticated") redirect("/login");
  if (kind === "session_expired") redirect("/auth/expired");
  if (kind === "forbidden") return <ForbiddenPanel />;

  const text = message ?? (error instanceof Error ? error.message : String(error));
  const isConfig = kind === "config";
  return (
    <div
      role="alert"
      className="rounded-lg border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 p-4"
    >
      <p className="text-sm font-medium text-[var(--color-danger)]">
        {isConfig ? "Cấu hình kết nối web → core sai" : "Không đọc được dữ liệu từ core API"}
      </p>
      <p className="mt-1 text-sm text-[var(--color-ink-muted)]">{text}</p>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-[var(--color-ink-muted)]">
        <li>
          Kiểm tra service đang chạy:{" "}
          <code className="rounded bg-black/30 px-1">docker compose ps</code>
        </li>
        <li>
          Xem log:{" "}
          <code className="rounded bg-black/30 px-1">
            docker compose logs -f api
          </code>
        </li>
        <li>
          Xác nhận <code className="rounded bg-black/30 px-1">API_KEY</code> trong
          .env khớp giữa api và web
        </li>
      </ul>
    </div>
  );
}
