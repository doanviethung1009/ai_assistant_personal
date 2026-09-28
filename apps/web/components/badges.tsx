import {
  NOTE_KIND_LABELS,
  PRIORITY_LABELS,
  STATUS_LABELS,
  type NoteKind,
  type TaskPriority,
  type TaskSource,
  type TaskStatus,
} from "@/lib/types";

const STATUS_STYLES: Record<TaskStatus, string> = {
  backlog: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
  todo: "bg-blue-500/15 text-blue-300 ring-blue-500/30",
  in_progress: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  blocked: "bg-red-500/15 text-red-300 ring-red-500/30",
  done: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  cancelled: "bg-zinc-500/15 text-zinc-400 ring-zinc-500/30",
};

const PRIORITY_STYLES: Record<TaskPriority, string> = {
  low: "bg-zinc-500/15 text-zinc-400 ring-zinc-500/30",
  medium: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  high: "bg-orange-500/15 text-orange-300 ring-orange-500/30",
  urgent: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
};

const BASE =
  "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset";

export function StatusBadge({ status }: { status: TaskStatus }) {
  return (
    <span className={`${BASE} ${STATUS_STYLES[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  );
}

export function PriorityBadge({ priority }: { priority: TaskPriority }) {
  return (
    <span className={`${BASE} ${PRIORITY_STYLES[priority]}`}>
      {PRIORITY_LABELS[priority]}
    </span>
  );
}

export function SourceBadge({ source }: { source: TaskSource }) {
  if (source === "manual") return null;
  return (
    <span className={`${BASE} bg-violet-500/15 text-violet-300 ring-violet-500/30`}>
      {source}
    </span>
  );
}

export function ProjectBadge({
  projectKey,
  color,
}: {
  projectKey: string;
  color: string | null;
}) {
  return (
    <span
      className={`${BASE} bg-white/5 ring-white/10`}
      style={color ? { color } : undefined}
    >
      {projectKey}
    </span>
  );
}

const NOTE_KIND_STYLES: Record<NoteKind, string> = {
  command: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  sql: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  text: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
  config: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  code: "bg-violet-500/15 text-violet-300 ring-violet-500/30",
};

export function NoteKindBadge({ kind }: { kind: NoteKind }) {
  return (
    <span className={`${BASE} ${NOTE_KIND_STYLES[kind]}`}>
      {NOTE_KIND_LABELS[kind]}
    </span>
  );
}

/** Cảnh báo nội dung có thể phá dữ liệu nếu đem chạy. */
export function DangerBadge() {
  return (
    <span
      className={`${BASE} bg-red-500/15 text-red-300 ring-red-500/40`}
      title="Lệnh này có thể gây mất dữ liệu. Đọc lại trước khi chạy."
    >
      cẩn thận
    </span>
  );
}

export function TagBadge({ tag }: { tag: string }) {
  return (
    <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs text-[var(--color-ink-muted)] ring-1 ring-inset ring-[var(--color-border)]">
      #{tag}
    </span>
  );
}
