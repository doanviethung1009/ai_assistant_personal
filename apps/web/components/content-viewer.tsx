"use client";

import { useState } from "react";
import { X, Eye } from "lucide-react";
import { Markdown } from "@/components/markdown";

export function ContentViewer({ content, title = "Nội dung chi tiết", isMarkdown = false }: { content: string, title?: string, isMarkdown?: boolean }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <div className="mt-1 relative rounded-md bg-black/20 p-3 text-sm text-[var(--color-ink-muted)] group">
        <div className="line-clamp-2 pr-24 text-ellipsis overflow-hidden">
          {content}
        </div>
        <button
          onClick={() => setIsOpen(true)}
          className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1.5 rounded-md bg-[var(--color-surface-hover)] px-2.5 py-1.5 text-xs font-medium text-[var(--color-ink)] opacity-0 transition-all hover:bg-[var(--color-accent)] hover:text-white group-hover:opacity-100"
        >
          <Eye className="size-3.5" />
          Xem chi tiết
        </button>
      </div>

      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
          <div 
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setIsOpen(false)}
          />
          <div className="relative w-full max-w-5xl max-h-full overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl flex flex-col animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between border-b border-[var(--color-border)] px-5 py-4 bg-[var(--color-surface-raised)]">
              <h3 className="text-base font-semibold text-white flex items-center gap-2">
                <Eye className="size-4 text-[var(--color-accent)]" />
                {title}
              </h3>
              <button
                onClick={() => setIsOpen(false)}
                className="rounded-md p-1.5 text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-hover)] hover:text-white transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-5 sm:p-6 bg-[#0d1117]">
              {isMarkdown ? (
                <div className="text-sm prose prose-invert max-w-none">
                  <Markdown>{content}</Markdown>
                </div>
              ) : (
                <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed text-[#c9d1d9]">
                  {content}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
