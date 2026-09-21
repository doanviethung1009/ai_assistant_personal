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
  tone?: "neutral" | "danger" | "warn" | "success";
  emptyMessage?: string;
}) {
  if (tasks.length === 0 && !emptyMessage) return null;

  const toneClass = {
    neutral: "text-[var(--color-ink)]",
    danger: "text-[var(--color-danger)]",
    warn: "text-[var(--color-warn)]",
    success: "text-[var(--color-success)]",
  }[tone];

  return (
    <section className="mt-6">
      <h2 className={`mb-3 flex items-center gap-2 text-sm font-semibold ${toneClass}`}>
        {title}
        <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs font-normal text-[var(--color-ink-muted)]">
          {tasks.length}
        </span>
      </h2>

      {tasks.length === 0 ? (
        <p className="rounded-lg border border-dashed border-[var(--color-border)] p-4 text-sm text-[var(--color-ink-muted)]">
          {emptyMessage}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {tasks.map((task) => (
            <TaskItem key={task.id} task={task} />
          ))}
        </ul>
      )}
    </section>
  );
}
