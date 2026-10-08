"use client";

import { useState } from "react";
import { setCurrentUserAction } from "@/app/actions-user";

export function CurrentUserManager({ initialUsers, assignees = [] }: { initialUsers: string[], assignees?: string[] }) {
  const [userText, setUserText] = useState((initialUsers || []).join(", "));
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setMessage(null);
    try {
      const names = userText.split(",").map(n => n.trim()).filter(Boolean);
      const result = await setCurrentUserAction(names);
      if (result.ok) {
        setMessage({ text: "Đã lưu thành công. Bảng Hôm nay và Tất cả Task sẽ chỉ hiện task của các thành viên này.", type: "success" });
      } else {
        setMessage({ text: "Lỗi: " + (result.error ?? "không lưu được"), type: "error" });
      }
    } catch {
      setMessage({ text: "Lỗi: không gọi được máy chủ", type: "error" });
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4">
      <h2 className="text-sm font-semibold">Tên người dùng cá nhân (Current Users)</h2>
      <p className="mt-1 mb-4 text-xs text-[var(--color-ink-muted)]">
        Điền Tên hiển thị (Display Name) của bạn và đồng đội trên hệ thống (hoặc trên Jira), ngăn cách bằng dấu phẩy.
        Tính năng này dùng để <strong>lọc riêng các task của những người này</strong> trên màn hình Dashboard (Hôm nay) và Tất cả Task. Các task của người khác sẽ được chuyển sang màn hình Giao việc (Team).
      </p>

      <form onSubmit={handleSave} className="flex flex-col gap-3">
        <div>
          <input
            type="text"
            value={userText}
            onChange={(e) => setUserText(e.target.value)}
            placeholder="VD: Đoàn Việt Hưng, Nguyễn Văn A"
            className="w-full max-w-sm rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm"
          />
          {assignees.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2 max-w-sm">
              <span className="text-xs text-[var(--color-ink-muted)] py-1">Gợi ý:</span>
              {assignees.map(a => {
                const isSelected = userText.split(",").map(n => n.trim()).includes(a);
                if (isSelected) return null;
                return (
                  <button
                    key={a}
                    type="button"
                    onClick={() => {
                      const current = userText.split(",").map(n => n.trim()).filter(Boolean);
                      setUserText([...current, a].join(", "));
                    }}
                    className="rounded-full bg-[var(--color-surface-hover)] px-2 py-1 text-xs border border-[var(--color-border)] hover:bg-[var(--color-border)] transition-colors"
                  >
                    + {a}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="flex items-center gap-4">
          <button
            type="submit"
            disabled={loading}
            className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {loading ? "Đang lưu..." : "Lưu cài đặt"}
          </button>
          {message && (
            <span className={`text-sm ${message.type === "success" ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
              {message.text}
            </span>
          )}
        </div>
      </form>
    </section>
  );
}
