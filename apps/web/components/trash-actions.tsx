"use client";

import { useState, useTransition } from "react";

import { emptyTrashAction, purgeExpiredAction } from "@/app/actions";

const BUTTON =
  "rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm transition-colors hover:bg-[var(--color-surface-hover)] disabled:opacity-40";

export function TrashActions({ total }: { total: number }) {
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
            : `${label}: đã xoá vĩnh viễn ${result.purged} task.`,
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
          onClick={() => run(purgeExpiredAction, "Dọn quá hạn")}
          className={BUTTON}
        >
          Dọn task đã quá hạn
        </button>

        {confirmingEmpty ? (
          <>
            <button
              type="button"
              disabled={pending}
              onClick={() => run(emptyTrashAction, "Dọn sạch")}
              className="rounded-md border border-[var(--color-danger)] px-3 py-1.5 text-sm text-[var(--color-danger)]"
            >
              Xác nhận xoá hết {total} task
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
            Dọn sạch thùng rác
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
