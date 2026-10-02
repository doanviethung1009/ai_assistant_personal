"use client";

import { useState, useTransition } from "react";
import { renameTagAction, deleteTagAction } from "@/app/actions";
import type { TagStat } from "@/lib/api";

export function TagManager({ initialTags }: { initialTags: TagStat[] }) {
  const [tags, setTags] = useState<TagStat[]>(initialTags);
  const [pending, startTransition] = useTransition();

  const [editingTag, setEditingTag] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  const handleRename = (oldName: string) => {
    if (!editValue.trim() || editValue.trim() === oldName) {
      setEditingTag(null);
      return;
    }
    const newName = editValue.trim().toLowerCase();

    startTransition(async () => {
      await renameTagAction(oldName, newName);
      // Update local state optimism
      setTags(prev => {
        let exists = prev.find(t => t.name === newName);
        const oldTag = prev.find(t => t.name === oldName);
        if (!oldTag) return prev;
        
        let next = prev.filter(t => t.name !== oldName);
        if (exists) {
          next = next.map(t => t.name === newName ? { ...t, taskCount: t.taskCount + oldTag.taskCount, noteCount: t.noteCount + oldTag.noteCount } : t);
        } else {
          next.push({ ...oldTag, name: newName });
        }
        return next.sort((a, b) => a.name.localeCompare(b.name));
      });
      setEditingTag(null);
    });
  };

  const handleDelete = (name: string) => {
    if (!confirm(`Bạn có chắc muốn xoá tag #${name} khỏi tất cả các task và sổ tay? Hành động này không thể hoàn tác.`)) return;

    startTransition(async () => {
      await deleteTagAction(name);
      setTags(prev => prev.filter(t => t.name !== name));
    });
  };

  return (
    <div className="flex flex-col gap-4">
      {tags.length === 0 ? (
        <p className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-ink-muted)]">
          Chưa có tag nào trong hệ thống.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {tags.map(tag => (
            <li key={tag.name} className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3">
              {editingTag === tag.name ? (
                <div className="flex flex-1 items-center gap-2">
                  <span className="text-[var(--color-ink-muted)]">#</span>
                  <input
                    type="text"
                    value={editValue}
                    onChange={e => setEditValue(e.target.value)}
                    className="flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-sm font-medium"
                    autoFocus
                    onKeyDown={e => {
                      if (e.key === 'Enter') handleRename(tag.name);
                      if (e.key === 'Escape') setEditingTag(null);
                    }}
                  />
                  <button
                    onClick={() => handleRename(tag.name)}
                    disabled={pending}
                    className="rounded bg-green-600 px-3 py-1 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
                  >
                    Lưu
                  </button>
                  <button
                    onClick={() => setEditingTag(null)}
                    className="rounded bg-gray-500 px-3 py-1 text-xs font-medium text-white hover:bg-gray-600"
                  >
                    Hủy
                  </button>
                </div>
              ) : (
                <>
                  <div className="flex flex-col">
                    <span className="text-sm font-semibold">#{tag.name}</span>
                    <span className="text-xs text-[var(--color-ink-muted)] mt-0.5">
                      {tag.taskCount} task • {tag.noteCount} sổ tay
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => { setEditingTag(tag.name); setEditValue(tag.name); }}
                      disabled={pending}
                      className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-xs font-medium transition-colors hover:bg-[var(--color-surface-hover)] disabled:opacity-50"
                    >
                      Sửa
                    </button>
                    <button
                      onClick={() => handleDelete(tag.name)}
                      disabled={pending}
                      className="rounded border border-red-500/30 bg-red-500/10 px-3 py-1 text-xs font-medium text-red-600 transition-colors hover:bg-red-500/20 disabled:opacity-50 dark:text-red-400"
                    >
                      Xoá
                    </button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
