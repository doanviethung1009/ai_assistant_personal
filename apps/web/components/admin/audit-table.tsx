import { formatDateTime } from "@/lib/format";
import type { AuditEntry } from "@/lib/types";

/**
 * Bảng nhật ký (server component). `details` là JSON do hệ thống ghi nhưng có thể chứa chuỗi từ người
 * dùng (tên, alias): render bằng text node trong <pre>, KHÔNG dangerouslySetInnerHTML. core đã lọc khoá
 * nhạy cảm (mật khẩu, token) trước khi ghi nên đây chỉ hiển thị lại.
 */
export function AuditTable({ entries, tz }: { entries: AuditEntry[]; tz: string }) {
  if (entries.length === 0) {
    return (
      <p className="rounded-md border border-[var(--color-border)] px-4 py-6 text-center text-sm text-[var(--color-ink-muted)]">
        Không có bản ghi nào khớp bộ lọc.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
      <table className="w-full text-left text-sm">
        <thead className="bg-[var(--color-surface-raised)] text-xs uppercase tracking-wide text-[var(--color-ink-muted)]">
          <tr>
            <th className="px-3 py-2">Thời gian</th>
            <th className="px-3 py-2">Hành động</th>
            <th className="px-3 py-2">Người thực hiện</th>
            <th className="px-3 py-2">Đối tượng</th>
            <th className="px-3 py-2">IP</th>
            <th className="px-3 py-2">Chi tiết</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--color-border)]">
          {entries.map((e) => (
            <tr key={e.id} className="align-top">
              <td className="whitespace-nowrap px-3 py-2 text-xs text-[var(--color-ink-muted)]">{formatDateTime(e.created_at, tz)}</td>
              <td className="px-3 py-2">
                <code className="text-xs">{e.action.slice(0, 64)}</code>
              </td>
              <td className="px-3 py-2 text-xs">{e.actor_email ? e.actor_email.slice(0, 120) : e.actor_user_id ? "(đã xoá)" : "Hệ thống"}</td>
              <td className="px-3 py-2 text-xs">
                {e.target_email ? e.target_email.slice(0, 120) : e.target_id ? e.target_id.slice(0, 40) : "-"}
                {e.target_type ? <span className="block text-[var(--color-ink-muted)]">{e.target_type.slice(0, 40)}</span> : null}
              </td>
              <td className="px-3 py-2 text-xs text-[var(--color-ink-muted)]">{e.client_ip ?? "-"}</td>
              <td className="px-3 py-2">
                {e.details ? (
                  <pre className="max-w-md overflow-x-auto whitespace-pre-wrap break-words text-[11px] text-[var(--color-ink-muted)]">
                    {JSON.stringify(e.details, null, 1).slice(0, 2000)}
                  </pre>
                ) : (
                  "-"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
