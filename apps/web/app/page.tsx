import { ApiErrorPanel } from "@/components/api-error";
import { JiraQuickSync } from "@/components/jira-quick-sync";
import { QuickAddForm } from "@/components/quick-add-form";
import { StatsStrip } from "@/components/stats-strip";
import { TaskSection } from "@/components/task-section";
import { getAgenda, getStats, listProjects } from "@/lib/api";
import { formatFullPlainDate } from "@/lib/format";
import type { Agenda, Project, Stats } from "@/lib/types";
import { CalendarDays } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function TodayPage() {
  let agenda: Agenda;
  let stats: Stats;
  let projects: Project[];

  try {
    [agenda, stats, projects] = await Promise.all([
      getAgenda({ view: "mine" }),
      getStats({ view: "mine" }),
      listProjects(),
    ]);
  } catch (error) {
    return (
      <ApiErrorPanel
        message={error instanceof Error ? error.message : String(error)}
      />
    );
  }

  const nothingToDo =
    agenda.overdue.length === 0 &&
    agenda.scheduled_today.length === 0 &&
    agenda.in_progress.length === 0;

  return (
    <div className="flex flex-col gap-8 pb-12 max-w-6xl mx-auto w-full">
      <div className="flex items-start justify-between relative">
        <div className="absolute -inset-1 bg-gradient-to-r from-blue-500 to-emerald-500 rounded-lg blur opacity-10 pointer-events-none"></div>
        <div className="relative">
          <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-[var(--color-ink)] to-gray-400 bg-clip-text text-transparent flex items-center gap-3">
            <div className="p-2 bg-[var(--color-accent)]/10 rounded-xl">
              <CalendarDays className="size-7 text-[var(--color-accent)]" />
            </div>
            Hôm nay
          </h1>
          <p className="mt-2 text-sm text-[var(--color-ink-muted)] font-medium tracking-wide">
            {formatFullPlainDate(agenda.reference_date)}
          </p>
        </div>
        <div className="relative z-10">
          <JiraQuickSync />
        </div>
      </div>

      <StatsStrip stats={stats} />

      <div className="relative rounded-2xl bg-gradient-to-br from-[var(--color-surface-raised)] to-[var(--color-surface)] p-2 shadow-sm border border-[var(--color-border)]">
        <QuickAddForm projects={projects} defaultScheduleToday />
      </div>

      {nothingToDo ? (
        <div className="rounded-2xl border border-dashed border-emerald-500/30 bg-emerald-500/5 p-12 text-center shadow-inner mt-4">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10 mb-4 shadow-sm">
            <CalendarDays className="size-8 text-emerald-500" />
          </div>
          <p className="text-base font-bold text-[var(--color-ink)]">Tuyệt vời! Bạn đã hoàn thành hết mục tiêu hôm nay.</p>
          <p className="mt-2 text-sm text-[var(--color-ink-muted)] max-w-sm mx-auto leading-relaxed">
            Thêm task ở trên, hoặc mở <span className="font-bold text-[var(--color-ink)]">Tất cả task</span> rồi bấm
            &ldquo;Hôm nay&rdquo; để xếp lịch tiếp theo nhé.
          </p>
        </div>
      ) : null}

      <div className="flex flex-col gap-4">
        <TaskSection title="Quá hạn" tasks={agenda.overdue} tone="danger" />
        <TaskSection title="Đang làm" tasks={agenda.in_progress} tone="warn" />
        <TaskSection title="Đã xếp cho hôm nay" tasks={agenda.scheduled_today} tone="accent" />
        <TaskSection
          title="Sắp đến hạn trong 7 ngày"
          tasks={agenda.due_soon}
        />
        <TaskSection
          title="Đã xong hôm nay"
          tasks={agenda.completed_today}
          tone="success"
        />
      </div>
    </div>
  );
}
