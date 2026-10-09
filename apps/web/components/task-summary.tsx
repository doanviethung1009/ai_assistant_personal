import { StatCard } from "@/components/stats-strip";
import type { ProjectProgress, Stats } from "@/lib/types";
import { AlertTriangle, CheckCircle2, CircleDot, Flame, Loader, OctagonX } from "lucide-react";

/** Số project hiện sẵn; phần còn lại gộp vào một dòng "và N project khác". */
const MAX_PROJECTS_SHOWN = 8;

/**
 * Dải tóm tắt phía trên danh sách task: nhìn một lần biết việc đang ở đâu.
 *
 * Số liệu theo mục xem (view) đang chọn, KHÔNG theo ô lọc q/trạng thái/khoảng thời gian bên
 * dưới: đó là bức tranh tổng của mục, còn bộ lọc chỉ thu hẹp danh sách. Nếu gộp cả hai thì
 * số trên thẻ và số dòng trong bảng sẽ lệch nhau và gây hiểu nhầm.
 * `by_priority` của backend chỉ đếm task đang mở nên "Gấp / Cao" không lẫn task đã xong.
 * Tỉ lệ theo project = task xong / task chưa huỷ; backend đã loại task đã huỷ khỏi mẫu số.
 */
export function TaskSummary({ stats }: { stats: Stats }) {
  const done7 = Object.values(stats.completed_last_7_days).reduce((a, b) => a + b, 0);
  const inProgress = stats.by_status.in_progress ?? 0;
  const blocked = stats.by_status.blocked ?? 0;
  const hot = (stats.by_priority.urgent ?? 0) + (stats.by_priority.high ?? 0);

  const projects = stats.by_project ?? [];

  return (
    <section aria-label="Tóm tắt task" className="flex flex-col gap-3">
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <StatCard label="Đang mở" value={stats.open_total} tone="accent" icon={CircleDot} />
      <StatCard
        label="Quá hạn"
        value={stats.overdue_total}
        tone={stats.overdue_total > 0 ? "danger" : "neutral"}
        icon={AlertTriangle}
      />
      <StatCard label="Đang làm" value={inProgress} icon={Loader} />
      <StatCard
        label="Bị chặn"
        value={blocked}
        tone={blocked > 0 ? "danger" : "neutral"}
        icon={OctagonX}
      />
      <StatCard
        label="Gấp / Cao"
        value={hot}
        tone={hot > 0 ? "accent" : "neutral"}
        icon={Flame}
      />
      <StatCard
        label="Xong 7 ngày"
        value={done7}
        tone={done7 > 0 ? "success" : "neutral"}
        icon={CheckCircle2}
      />
    </dl>
    {projects.length > 0 && <ProjectProgressList projects={projects} />}
    </section>
  );
}

/**
 * Thanh tiến độ từng project. Màu theo màu project (nếu có), nên giá trị % luôn được in ra
 * bằng chữ, không chỉ dựa vào độ dài thanh hay màu.
 */
function ProjectProgressList({ projects }: { projects: ProjectProgress[] }) {
  const shown = projects.slice(0, MAX_PROJECTS_SHOWN);
  const hidden = projects.length - shown.length;
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4">
      <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-ink-muted)]">
        Tiến độ theo project
      </h2>
      <ul className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
        {shown.map((p) => (
          <li key={p.project_id ?? "none"}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
              <span className="truncate font-medium" title={p.name}>
                {p.key ? <span className="mr-1.5 text-xs opacity-60">{p.key}</span> : null}
                {p.name}
              </span>
              <span className="shrink-0 tabular-nums text-[var(--color-ink-muted)]">
                {p.done}/{p.total} · <strong className="text-[var(--color-ink)]">{p.percent_done}%</strong>
              </span>
            </div>
            <div
              role="progressbar"
              aria-label={`Tiến độ ${p.name}`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={p.percent_done}
              className="h-2 overflow-hidden rounded-full bg-[var(--color-border)]"
            >
              <div
                className="h-full rounded-full bg-blue-500 transition-all"
                style={{ width: `${p.percent_done}%`, backgroundColor: p.color ?? undefined }}
              />
            </div>
          </li>
        ))}
      </ul>
      {hidden > 0 && (
        <p className="mt-3 text-xs text-[var(--color-ink-muted)]">và {hidden} project khác</p>
      )}
    </div>
  );
}
