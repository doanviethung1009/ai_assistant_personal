import { formatMinutes } from "@/lib/format";
import type { Stats } from "@/lib/types";

function StatCard({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string | number;
  tone?: "neutral" | "danger" | "success";
}) {
  const toneClass = {
    neutral: "text-[var(--color-ink)]",
    danger: "text-[var(--color-danger)]",
    success: "text-[var(--color-success)]",
  }[tone];

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-4 py-3">
      <dt className="text-xs text-[var(--color-ink-muted)]">{label}</dt>
      <dd className={`mt-1 text-xl font-semibold tabular-nums ${toneClass}`}>
        {value}
      </dd>
    </div>
  );
}

export function StatsStrip({ stats }: { stats: Stats }) {
  const completedToday =
    stats.completed_last_7_days[stats.reference_date] ?? 0;

  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatCard label="Việc đang mở" value={stats.open_total} />
      <StatCard
        label="Quá hạn"
        value={stats.overdue_total}
        tone={stats.overdue_total > 0 ? "danger" : "neutral"}
      />
      <StatCard
        label="Xong hôm nay"
        value={completedToday}
        tone={completedToday > 0 ? "success" : "neutral"}
      />
      <StatCard
        label="Thời gian đã ghi"
        value={formatMinutes(stats.minutes_logged_today)}
      />
    </dl>
  );
}
