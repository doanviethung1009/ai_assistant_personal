"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { useActionAuth } from "@/lib/use-action-auth";
import { deleteTagRuleAction } from "@/app/actions";
import { formatDateTime } from "@/lib/format";
import type { TagRule } from "@/lib/api";

/**
 * Danh sách quy tắc đồng bộ tag của MỘT trang (phân trang do page.tsx lo qua ?rulesPage=).
 * `canDelete` chỉ để ẩn nút; quyền thật do Server Action và core kiểm.
 */
export function TagRuleList({
  rules,
  canDelete,
  tz,
}: {
  rules: TagRule[];
  canDelete: boolean;
  tz: string;
}) {
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const gate = useActionAuth();
  const router = useRouter();

  const handleRemove = (rule: TagRule) => {
    if (!confirm(`Gỡ quy tắc cho #${rule.sourceTag}? Lần đồng bộ tới, tag này sẽ quay lại task.`)) return;
    startTransition(async () => {
      setError(null);
      const result = await deleteTagRuleAction(rule.id);
      if (gate(result)) return;
      if (!result.ok) {
        setError(result.error ?? "Gỡ quy tắc thất bại");
        return;
      }
      router.refresh();
    });
  };

  return (
    <div className="flex flex-col gap-2">
      {error ? (
        <p role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-600">
          {error}
        </p>
      ) : null}
      {rules.length === 0 ? (
        <p className="rounded-lg border border-dashed border-[var(--color-border)] p-4 text-center text-sm text-[var(--color-ink-muted)]">
          Chưa có quy tắc nào. Đổi tên hoặc xoá một tag có trên task công việc để tạo.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {rules.map((rule) => (
            <li
              key={rule.id}
              className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3"
            >
              <div className="flex flex-col">
                <span className="text-sm font-semibold">
                  #{rule.sourceTag}{" "}
                  {rule.targetTag ? (
                    <>
                      <span aria-hidden className="text-[var(--color-ink-muted)]">→</span> #{rule.targetTag}
                    </>
                  ) : (
                    <span className="font-normal text-red-600 dark:text-red-400">(bị chặn)</span>
                  )}
                </span>
                <span className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
                  {rule.createdByName ?? "Không rõ người tạo"} • {formatDateTime(rule.createdAt, tz)}
                </span>
              </div>
              {canDelete ? (
                <button
                  onClick={() => handleRemove(rule)}
                  disabled={pending}
                  className="rounded border border-red-500/30 bg-red-500/10 px-3 py-1 text-xs font-medium text-red-600 transition-colors hover:bg-red-500/20 disabled:opacity-50 dark:text-red-400"
                >
                  Gỡ
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
