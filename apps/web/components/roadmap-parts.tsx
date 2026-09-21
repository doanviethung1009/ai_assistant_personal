import {
  STATUS_LABELS,
  countByStatus,
  progressPercent,
  type FlowItem,
  type ItemStatus,
  type Phase,
} from "@/lib/roadmap";

const STATUS_STYLES: Record<ItemStatus, string> = {
  done: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  partial: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  doing: "bg-blue-500/15 text-blue-300 ring-blue-500/30",
  planned: "bg-zinc-500/15 text-zinc-400 ring-zinc-500/30",
};

const MARKERS: Record<ItemStatus, string> = {
  done: "✓",
  partial: "~",
  doing: "→",
  planned: "·",
};

const MARKER_COLORS: Record<ItemStatus, string> = {
  done: "text-emerald-400",
  partial: "text-amber-400",
  doing: "text-blue-400",
  planned: "text-zinc-500",
};

export function StatusPill({ status }: { status: ItemStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_STYLES[status]}`}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

export function ProgressBar({ percent }: { percent: number }) {
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-white/5"
      role="progressbar"
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Hoàn thành ${percent} phần trăm`}
    >
      <div
        className="h-full rounded-full bg-[var(--color-accent)] transition-all"
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}

/** Dải bước ngang cho 5 phase. Xuống dòng thành dọc trên màn hình nhỏ. */
export function PhaseFlow({ phases }: { phases: Phase[] }) {
  return (
    <ol className="flex flex-col gap-2 sm:flex-row sm:items-stretch sm:gap-0">
      {phases.map((phase, index) => {
        const percent = progressPercent(phase.items);
        const isLast = index === phases.length - 1;

        return (
          <li key={phase.key} className="flex flex-1 items-stretch gap-2">
            <a
              href={`#phase-${phase.id}`}
              className="flex min-w-0 flex-1 flex-col gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3 transition-colors hover:bg-[var(--color-surface-hover)]"
            >
              <div className="flex items-center gap-2">
                <span
                  className={`flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ring-1 ring-inset ${STATUS_STYLES[phase.status]}`}
                >
                  {phase.id}
                </span>
                <span className="truncate text-xs font-medium">{phase.title}</span>
              </div>

              <ProgressBar percent={percent} />

              <span className="text-xs text-[var(--color-ink-muted)]">
                {percent}% · {STATUS_LABELS[phase.status]}
              </span>
            </a>

            {!isLast ? (
              <span
                aria-hidden="true"
                className="hidden shrink-0 self-center px-1 text-[var(--color-ink-muted)] sm:block"
              >
                →
              </span>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

export function ItemList({ items }: { items: FlowItem[] }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {items.map((item) => (
        <li key={item.label} className="flex gap-2 text-sm">
          <span
            aria-hidden="true"
            className={`mt-0.5 w-3 shrink-0 text-center font-mono ${MARKER_COLORS[item.status]}`}
          >
            {MARKERS[item.status]}
          </span>
          <span className="min-w-0">
            <span
              className={
                item.status === "planned"
                  ? "text-[var(--color-ink-muted)]"
                  : "text-[var(--color-ink)]"
              }
            >
              {item.label}
            </span>
            <span className="sr-only"> — {STATUS_LABELS[item.status]}</span>
            {item.note ? (
              <span className="block text-xs text-[var(--color-ink-muted)]">
                {item.note}
              </span>
            ) : null}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function StatusLegend({ items }: { items: FlowItem[] }) {
  const counts = countByStatus(items);
  const order: ItemStatus[] = ["done", "partial", "doing", "planned"];

  return (
    <dl className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
      {order.map((status) => (
        <div key={status} className="flex items-center gap-1.5">
          <span aria-hidden="true" className={`font-mono ${MARKER_COLORS[status]}`}>
            {MARKERS[status]}
          </span>
          <dt className="text-[var(--color-ink-muted)]">{STATUS_LABELS[status]}</dt>
          <dd className="tabular-nums">{counts[status]}</dd>
        </div>
      ))}
    </dl>
  );
}
