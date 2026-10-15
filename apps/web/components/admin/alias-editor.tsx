"use client";

import { useId, useState } from "react";

import { splitAliasText } from "@/lib/alias-input";

/**
 * Sửa alias Jira của MỘT người dùng (thay toàn bộ). Nhập cách nhau bằng dấu phẩy hoặc xuống dòng;
 * `suggestions` là các assignee đã thấy trong task (gợi ý, không bắt buộc). Kiểm tra thật (độ dài,
 * trùng, tối đa 20) nằm ở Server Action và core; ở đây chỉ tách chuỗi.
 */
export function AliasEditor({
  initial,
  suggestions,
  disabled,
  onSave,
  onCancel,
}: {
  initial: string[];
  suggestions: string[];
  disabled: boolean;
  onSave: (aliases: string[]) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState(initial.join(", "));
  const listId = useId();
  return (
    <div className="flex flex-col gap-2">
      <label className="text-xs text-[var(--color-ink-muted)]" htmlFor={`${listId}-input`}>
        Alias Jira (cách nhau bằng dấu phẩy)
      </label>
      <input
        id={`${listId}-input`}
        list={listId}
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={4100}
        className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm outline-none focus:border-[var(--color-accent)]"
      />
      <datalist id={listId}>
        {suggestions.slice(0, 200).map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={disabled}
          onClick={() =>
            onSave(
              splitAliasText(text)
                .map((s) => s.trim())
                .filter(Boolean),
            )
          }
          className="rounded-md bg-[var(--color-accent)] px-3 py-1 text-xs font-medium text-white disabled:opacity-60"
        >
          Lưu alias
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-[var(--color-border)] px-3 py-1 text-xs hover:bg-[var(--color-surface-hover)]"
        >
          Huỷ
        </button>
      </div>
    </div>
  );
}
