import { ApiErrorPanel } from "@/components/api-error";
import { QuickAddForm } from "@/components/quick-add-form";
import { StatsStrip } from "@/components/stats-strip";
import { TaskSection } from "@/components/task-section";
import { getAgenda, getStats, listProjects } from "@/lib/api";
import { formatFullPlainDate } from "@/lib/format";
import type { Agenda, Project, Stats } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function TodayPage() {
  let agenda: Agenda;
  let stats: Stats;
  let projects: Project[];

  try {
    [agenda, stats, projects] = await Promise.all([
      getAgenda(),
      getStats(),
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
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Hôm nay</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          {formatFullPlainDate(agenda.reference_date)}
        </p>
      </div>

      <StatsStrip stats={stats} />

      <QuickAddForm projects={projects} defaultScheduleToday />

      {nothingToDo ? (
        <p className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-ink-muted)]">
          Chưa có việc nào cho hôm nay. Thêm task ở trên, hoặc mở{" "}
          <span className="text-[var(--color-ink)]">Tất cả task</span> rồi bấm
          &ldquo;Hôm nay&rdquo; để xếp lịch.
        </p>
      ) : null}

      <TaskSection title="Quá hạn" tasks={agenda.overdue} tone="danger" />
      <TaskSection title="Đang làm" tasks={agenda.in_progress} tone="warn" />
      <TaskSection title="Đã xếp cho hôm nay" tasks={agenda.scheduled_today} />
      <TaskSection
        title="Sắp đến hạn trong 7 ngày, chưa xếp lịch"
        tasks={agenda.due_soon}
      />
      <TaskSection
        title="Đã xong hôm nay"
        tasks={agenda.completed_today}
        tone="success"
      />
    </div>
  );
}
