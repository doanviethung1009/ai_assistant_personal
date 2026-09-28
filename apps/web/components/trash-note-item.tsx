"use client";

import { useState, useTransition } from "react";

import { purgeNoteAction, restoreNoteAction } from "@/app/actions";
import { DangerBadge, NoteKindBadge, ProjectBadge } from "@/components/badges";
import { formatDateTime } from "@/lib/format";
import type { Note } from "@/lib/types";

const BUTTON =
  "rounded-md border border-[var(--color-border)] px-2.5 py-1 text-xs transition-colors hover:bg-[var(--color-surface-hover)] disabled:opacity-40";

function remainingTone(days: number | null): string {
  if (days === null) return "text-[var(--color-ink-muted)]";
  if (days <= 3) return "text-[var(--color-danger)]";
  if (days <= 7) return "text-[var(--color-warn)]";
  return "text-[var(--color-ink-muted)]";
}

export function TrashNoteItem({ note }: { note: Note }) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  function run(action: () => Promise<{ ok: boolean; error?: string }>) {
    setError(null);
    startTransition(async () => {
      const result = await action();
      if (!result.ok) setError(result.error ?? "Thao tác thất bại");
    });
  }

  const days = note.days_until_purge;
  // Chỉ hiện dòng đầu. Thùng rác là nơi để nhận ra mình đã xoá cái gì, không
  // phải nơi đọc nội dung; cần đọc đủ thì phục hồi rồi xem ở trang Sổ tay.
  const firstLine = note.content.split("\n", 1)[0] ?? "";
  const lineCount = note.content.split("\n").length;

  return (
    <li
      className={`rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3 transition-opacity ${
        pending ? "opacity-60" : ""
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-[var(--color-ink-muted)] line-through">
            {note.title}
          </p>

          {/* Text node, React tự escape. Không dùng dangerouslySetInnerHTML. */}
          <p className="mt-1 truncate font-mono text-xs text-[var(--color-ink-muted)]">
            {firstLine}
            {lineCount > 1 ? ` … (+${lineCount - 1} dòng)` : ""}
          </p>

          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <NoteKindBadge kind={note.kind} />
            {note.is_dangerous ? <DangerBadge /> : null}
            {note.project ? (
              <ProjectBadge
                projectKey={note.project.key}
                color={note.project.color}
              />
            ) : null}
          </div>

          <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--color-ink-muted)]">
            <div className="flex gap-1">
              <dt>Đã xoá:</dt>
              <dd>{formatDateTime(note.deleted_at)}</dd>
            </div>
            <div className="flex gap-1">
              <dt>Xoá vĩnh viễn sau:</dt>
              <dd className={`font-medium ${remainingTone(days)}`}>
                {days === null
                  ? "—"
                  : days === 0
                    ? "sắp tới, ở lần dọn kế tiếp"
                    : `${days} ngày`}
              </dd>
            </div>
          </dl>

          {error ? (
            <p role="alert" className="mt-2 text-xs text-[var(--color-danger)]">
              {error}
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 gap-1">
          <button
            type="button"
            disabled={pending}
            onClick={() => run(() => restoreNoteAction(note.id))}
            className={BUTTON}
          >
            Phục hồi
          </button>

          {confirming ? (
            <>
              <button
                type="button"
                disabled={pending}
                onClick={() => run(() => purgeNoteAction(note.id))}
                className="rounded-md border border-[var(--color-danger)] px-2.5 py-1 text-xs text-[var(--color-danger)]"
              >
                Xoá hẳn
              </button>
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className={BUTTON}
              >
                Huỷ
              </button>
            </>
          ) : (
            <button
              type="button"
              disabled={pending}
              onClick={() => setConfirming(true)}
              className={BUTTON}
              title="Xoá vĩnh viễn, không hoàn tác được"
            >
              Xoá vĩnh viễn
            </button>
          )}
        </div>
      </div>
    </li>
  );
}
