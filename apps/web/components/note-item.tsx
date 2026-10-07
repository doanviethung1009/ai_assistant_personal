"use client";

import { useState, useTransition } from "react";

import {
  archiveNoteAction,
  unarchiveNoteAction,
  deleteNoteAction,
  markNoteUsedAction,
  toggleNotePinAction,
} from "@/app/actions";
import { DangerBadge, NoteKindBadge, ProjectBadge, TagBadge } from "@/components/badges";
import { CopyButton } from "@/components/copy-button";
import { formatDateTime } from "@/lib/format";
import type { Note } from "@/lib/types";

const ACTION_CLASS =
  "rounded-md border border-[var(--color-border)] px-2 py-1 text-xs transition-colors hover:bg-[var(--color-surface-hover)] disabled:opacity-50";

/**
 * Một mục sổ tay. `archiveSupported` do trang truyền xuống (false khi
 * DATA_SOURCE là file/memory) để ẩn nút Lưu trữ: engine cục bộ chưa có
 * trạng thái này, bấm sẽ chỉ ra lỗi 501.
 */
export function NoteItem({
  note,
  archiveSupported,
}: {
  note: Note;
  archiveSupported: boolean;
}) {
  // archived_at là optional trong type sinh ra, nên `?? null` gộp cả undefined.
  const archivedAt = note.archived_at ?? null;
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [expanded, setExpanded] = useState(false);

  const lines = note.content.split("\n");
  const isLong = lines.length > 12;
  // Chỉ cắt khi thực sự dài. Cắt sớm làm người dùng phải bấm thêm một lần cho
  // thứ lẽ ra đọc được ngay.
  const shown = isLong && !expanded ? lines.slice(0, 12).join("\n") : note.content;

  function run(action: () => Promise<{ ok: boolean; error?: string }>) {
    setError(null);
    startTransition(async () => {
      const result = await action();
      if (!result.ok) setError(result.error ?? "Không thực hiện được");
    });
  }

  return (
    <li className="flex flex-col gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3">
      <div className="flex flex-wrap items-start gap-2">
        {note.is_pinned ? (
          <span aria-label="Đã ghim" title="Đã ghim" className="text-sm">
            📌
          </span>
        ) : null}

        <p className="min-w-0 flex-1 text-sm font-medium break-words">
          {note.title}
        </p>

        <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          <NoteKindBadge kind={note.kind} />
          {note.is_dangerous ? <DangerBadge /> : null}
          {note.project ? (
            <ProjectBadge
              projectKey={note.project.key}
              color={note.project.color}
            />
          ) : null}
        </div>
      </div>

      {note.description ? (
        <p className="text-xs text-[var(--color-ink-muted)]">{note.description}</p>
      ) : null}

      {note.context ? (
        <p className="text-xs text-[var(--color-ink-muted)]">
          Áp dụng ở: <span className="font-medium">{note.context}</span>
        </p>
      ) : null}

      {/*
        Nội dung render bằng text node của JSX. Đây là chỗ duy nhất nội dung do
        người dùng nhập xuất hiện nguyên văn, và React tự escape nên HTML dán
        vào chỉ hiện ra dưới dạng chữ. KHÔNG đổi sang dangerouslySetInnerHTML.
      */}
      <pre className="overflow-x-auto rounded-md border border-[var(--color-border)] bg-black/30 p-3 text-xs leading-relaxed">
        <code className="font-mono">{shown}</code>
      </pre>

      {isLong ? (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="self-start text-xs text-[var(--color-ink-muted)] underline"
        >
          {expanded
            ? "Thu lại"
            : `Xem đủ ${lines.length} dòng`}
        </button>
      ) : null}

      {note.tags.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {note.tags.map((tag) => (
            <TagBadge key={tag} tag={tag} />
          ))}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <CopyButton
          value={note.content}
          confirmMessage={
            note.is_dangerous
              ? `"${note.title}" được đánh dấu cẩn thận. Đọc lại nội dung trước khi chạy. Vẫn copy?`
              : null
          }
          onCopied={() => {
            // Không bọc trong startTransition: đây là ghi nhận nền, không nên
            // làm nút chuyển sang trạng thái pending.
            void markNoteUsedAction(note.id);
          }}
        />

        <button
          type="button"
          disabled={pending}
          onClick={() => run(() => toggleNotePinAction(note.id, !note.is_pinned))}
          className={ACTION_CLASS}
        >
          {note.is_pinned ? "Bỏ ghim" : "Ghim"}
        </button>

        {archiveSupported ? (
          <button
            type="button"
            disabled={pending}
            onClick={() =>
              run(() =>
                archivedAt === null
                  ? archiveNoteAction(note.id)
                  : unarchiveNoteAction(note.id),
              )
            }
            className={ACTION_CLASS}
          >
            {archivedAt === null ? "Lưu trữ" : "Bỏ lưu trữ"}
          </button>
        ) : null}

        <button
          type="button"
          disabled={pending}
          onClick={() => run(() => deleteNoteAction(note.id))}
          className={ACTION_CLASS}
        >
          Xoá
        </button>

        <span className="ml-auto text-xs text-[var(--color-ink-muted)]">
          {note.use_count > 0
            ? `Đã dùng ${note.use_count} lần, gần nhất ${formatDateTime(note.last_used_at)}`
            : "Chưa dùng lần nào"}
          {archivedAt !== null
            ? ` · Lưu trữ lúc ${formatDateTime(archivedAt)}`
            : ""}
        </span>
      </div>

      {error ? (
        <p role="alert" className="text-xs text-[var(--color-danger)]">
          {error}
        </p>
      ) : null}
    </li>
  );
}
