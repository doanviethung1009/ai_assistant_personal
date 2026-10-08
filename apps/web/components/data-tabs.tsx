import Link from "next/link";

/**
 * Các tab của trang Dữ liệu. Chọn bằng `?tab=` nên là Server Component thuần,
 * không cần JS và link chia sẻ được.
 *
 * Vì sao có: trước đây cả xuất, nhập, đồng bộ Jira, Chrome, Vault và vùng nguy
 * hiểm nằm chung một trang dài, người dùng phải cuộn mới thấy cái cần.
 */

export const DATA_TABS = [
  { id: "xuat", label: "Xuất dữ liệu", hint: "Backup JSON, CSV" },
  { id: "nhap", label: "Nhập dữ liệu", hint: "JSON, file, Vault" },
  { id: "dong-bo", label: "Đồng bộ & Cấu hình", hint: "Jira, URL, người dùng" },
  { id: "nguy-hiem", label: "Vùng nguy hiểm", hint: "Xoá dữ liệu" },
] as const;

export type DataTabId = (typeof DATA_TABS)[number]["id"];

/** Chỉ nhận giá trị nằm trong danh sách cứng; giá trị lạ về tab đầu tiên. */
export function parseDataTab(raw: string | undefined): DataTabId {
  return DATA_TABS.find((t) => t.id === raw)?.id ?? "xuat";
}

export function DataTabs({ active }: { active: DataTabId }) {
  return (
    <nav
      aria-label="Nhóm chức năng dữ liệu"
      className="flex flex-wrap gap-2 border-b border-[var(--color-border)] pb-3"
    >
      {DATA_TABS.map((tab) => {
        const isActive = tab.id === active;
        const danger = tab.id === "nguy-hiem";
        return (
          <Link
            key={tab.id}
            href={`/data?tab=${tab.id}`}
            aria-current={isActive ? "page" : undefined}
            className={`flex flex-col rounded-lg border px-4 py-2 text-left transition-colors ${
              isActive
                ? danger
                  ? "border-[var(--color-danger)]/50 bg-[var(--color-danger)]/10"
                  : "border-[var(--color-accent)] bg-[var(--color-accent)]/10"
                : "border-[var(--color-border)] bg-[var(--color-surface-raised)] hover:border-[var(--color-ink-muted)]/40"
            }`}
          >
            <span className={`text-sm font-medium ${danger && isActive ? "text-[var(--color-danger)]" : ""}`}>
              {tab.label}
            </span>
            <span className="text-[11px] text-[var(--color-ink-muted)]">{tab.hint}</span>
          </Link>
        );
      })}
    </nav>
  );
}

/**
 * Thông báo thay cho phần không dùng được ở chế độ DATA_SOURCE=api.
 * Trước đây người dùng bấm vào mới biết bị từ chối ("Chỉ hỗ trợ chế độ Local File").
 */
export function LocalOnlyNotice({ feature }: { feature: string }) {
  return (
    <div
      role="note"
      className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-5 text-sm text-[var(--color-ink-muted)]"
    >
      <p className="font-medium text-[var(--color-ink)]">{feature} chưa hỗ trợ ở chế độ Core API (Postgres)</p>
      <p className="mt-1 leading-relaxed">
        Tính năng này đọc và ghi trực tiếp vào kho dữ liệu cục bộ nên chỉ chạy khi{" "}
        <code>DATA_SOURCE=file</code> hoặc <code>memory</code>. Đổi nguồn: xem mục &quot;Hướng dẫn đổi nguồn dữ liệu&quot; ở
        đầu trang.
      </p>
    </div>
  );
}
