import { formatMinutes } from "@/lib/format";
import type { Stats } from "@/lib/types";
import { CircleDot, Clock, CheckCircle2, AlertTriangle } from "lucide-react";

export function StatCard({
  label,
  value,
  tone = "neutral",
  icon: Icon,
}: {
  label: string;
  value: string | number;
  tone?: "neutral" | "danger" | "success" | "accent";
  icon: any;
}) {
  const toneClass = {
    neutral: "text-[var(--color-ink)] bg-[var(--color-surface-raised)] border-[var(--color-border)] hover:border-gray-500/30",
    danger: "text-red-600 bg-red-500/5 border-red-500/20 hover:border-red-500/40 dark:text-red-400",
    success: "text-emerald-600 bg-emerald-500/5 border-emerald-500/20 hover:border-emerald-500/40 dark:text-emerald-400",
    accent: "text-blue-600 bg-blue-500/5 border-blue-500/20 hover:border-blue-500/40 dark:text-blue-400",
  }[tone];

  const iconToneClass = {
    neutral: "text-gray-400 bg-gray-500/10",
    danger: "text-red-500 bg-red-500/10",
    success: "text-emerald-500 bg-emerald-500/10",
    accent: "text-blue-500 bg-blue-500/10",
  }[tone];

  return (
    <div className={`group relative overflow-hidden rounded-xl border p-4 transition-all duration-300 hover:-translate-y-1 hover:shadow-md ${toneClass}`}>
      <div className="absolute right-0 top-0 -mt-6 -mr-6 h-24 w-24 rounded-full bg-current opacity-[0.03] blur-xl transition-all duration-500 group-hover:scale-[2]"></div>
      <div className="flex items-center gap-3 relative z-10">
        <div className={`p-2 rounded-lg ${iconToneClass}`}>
          <Icon className="size-5" />
        </div>
        <div>
          <dt className="text-[0.8125rem] uppercase tracking-wider font-semibold opacity-70 mb-0.5">{label}</dt>
          <dd className="text-2xl font-bold tabular-nums tracking-tight">
            {value}
          </dd>
        </div>
      </div>
    </div>
  );
}

export function StatsStrip({ stats }: { stats: Stats }) {
  const completedToday =
    stats.completed_last_7_days[stats.reference_date] ?? 0;

  return (
    <dl className="grid grid-cols-2 gap-4 xl:grid-cols-4">
      <StatCard label="Việc đang mở" value={stats.open_total} tone="accent" icon={CircleDot} />
      <StatCard
        label="Quá hạn"
        value={stats.overdue_total}
        tone={stats.overdue_total > 0 ? "danger" : "neutral"}
        icon={AlertTriangle}
      />
      <StatCard
        label="Xong hôm nay"
        value={completedToday}
        tone={completedToday > 0 ? "success" : "neutral"}
        icon={CheckCircle2}
      />
      <StatCard
        label="Thời gian đã ghi"
        value={formatMinutes(stats.minutes_logged_today)}
        icon={Clock}
      />
    </dl>
  );
}
