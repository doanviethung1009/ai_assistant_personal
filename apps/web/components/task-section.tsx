import { TaskItem } from "@/components/task-item";
import type { Task } from "@/lib/types";

export function TaskSection({
  title,
  tasks,
  tone = "neutral",
  emptyMessage,
}: {
  title: string;
  tasks: Task[];
  tone?: "neutral" | "danger" | "warn" | "success" | "accent";
  emptyMessage?: string;
}) {
  if (tasks.length === 0 && !emptyMessage) return null;

  const toneClass = {
    neutral: "text-[var(--color-ink)] border-[var(--color-border)] bg-[var(--color-surface)]",
    danger: "text-red-600 border-red-500/20 bg-red-500/5 dark:text-red-400",
    warn: "text-amber-600 border-amber-500/20 bg-amber-500/5 dark:text-amber-400",
    success: "text-emerald-600 border-emerald-500/20 bg-emerald-500/5 dark:text-emerald-400",
    accent: "text-blue-600 border-blue-500/20 bg-blue-500/5 dark:text-blue-400",
  }[tone];

  const badgeToneClass = {
    neutral: "bg-gray-500/10 text-[var(--color-ink)]",
    danger: "bg-red-500/10 text-red-600 dark:text-red-400",
    warn: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
    success: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    accent: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  }[tone];

  return (
    <section className="mt-8">
      <div className={`mb-4 inline-flex items-center gap-3 rounded-xl border px-4 py-2 shadow-sm ${toneClass}`}>
        <h2 className="text-sm font-bold tracking-wide">
          {title}
        </h2>
        <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${badgeToneClass}`}>
          {tasks.length}
        </span>
      </div>

      {tasks.length === 0 ? (
        <p className="rounded-xl border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-ink-muted)] bg-[var(--color-surface-raised)]/50">
          {emptyMessage}
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {tasks.map((task) => (
            <TaskItem key={task.id} task={task} />
          ))}
        </ul>
      )}
    </section>
  );
}
