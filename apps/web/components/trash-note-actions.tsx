"use client";

import { useState, useTransition } from "react";

import { emptyNoteTrashAction, purgeExpiredNotesAction } from "@/app/actions";

const BUTTON =
  "rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm transition-colors hover:bg-[var(--color-surface-hover)] disabled:opacity-40";

/**
 * Bản song song của TrashActions dành cho sổ tay.
 *
 * Cố tình không gộp hai component thành một cái nhận entity làm tham số: chỉ
 * có bốn dòng khác nhau, còn gộp lại thì phải truyền vào cả nhãn, cả hai
 * action, và mỗi lần đọc phải lần theo tham số để biết nó đang xoá cái gì.
 * Với thao tác không hoàn tác được thì đọc thẳng quan trọng hơn là gọn.
 */
export function TrashNoteActions({ total }: { total: number }) {
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmingEmpty, setConfirmingEmpty] = useState(false);

  function run(
    action: () => Promise<{ ok: boolean; error?: string; purged?: number }>,
    label: string,
  ) {
    setError(null);
    setMessage(null);
    startTransition(async () => {
      const result = await action();
      if (result.ok) {
        setMessage(
          result.purged === 0
            ? `${label}: không có gì để xoá.`
            : `${label}: đã xoá vĩnh viễn ${result.purged} mục sổ tay.`,
        );
        setConfirmingEmpty(false);
      } else {
        setError(result.error ?? "Thao tác thất bại");
      }
    });
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={pending}
          onClick={() => run(purgeExpiredNotesAction, "Dọn quá hạn")}
          className={BUTTON}
        >
          Dọn mục đã quá hạn
        </button>

        {confirmingEmpty ? (
          <>
            <button
              type="button"
              disabled={pending}
              onClick={() => run(emptyNoteTrashAction, "Dọn sạch")}
              className="rounded-md border border-[var(--color-danger)] px-3 py-1.5 text-sm text-[var(--color-danger)]"
            >
              Xác nhận xoá hết {total} mục
            </button>
            <button
              type="button"
              onClick={() => setConfirmingEmpty(false)}
              className={BUTTON}
            >
              Huỷ
            </button>
          </>
        ) : (
          <button
            type="button"
            disabled={pending || total === 0}
            onClick={() => setConfirmingEmpty(true)}
            className={BUTTON}
          >
            Dọn sạch sổ tay đã xoá
          </button>
        )}
      </div>

      {message ? (
        <p role="status" className="text-xs text-[var(--color-success)]">
          {message}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-xs text-[var(--color-danger)]">
          {error}
        </p>
      ) : null}
    </div>
  );
}
