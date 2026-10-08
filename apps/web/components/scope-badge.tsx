import { SCOPE_LABELS, type TaskScope } from "@/lib/types";

const BASE =
  "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset";

const SCOPE_STYLES: Record<TaskScope, string> = {
  work: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  personal: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
};

/**
 * Nhãn "Công việc" / "Cá nhân" để User thấy ngay task có bị đồng bộ ghi đè hay không.
 * Chỉ render text node, nhãn lấy từ bảng cố định nên không có chỗ nào nội suy HTML.
 */
export function ScopeBadge({ scope }: { scope: TaskScope }) {
  return <span className={`${BASE} ${SCOPE_STYLES[scope]}`}>{SCOPE_LABELS[scope]}</span>;
}
