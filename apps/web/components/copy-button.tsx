"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Nút copy nội dung vào clipboard.
 *
 * Có hai đường vì navigator.clipboard chỉ tồn tại trong secure context.
 * http://localhost được tính là secure, nhưng mở app qua IP trong LAN
 * (http://192.168.1.10:3000) thì KHÔNG, và navigator.clipboard sẽ là
 * undefined. Vì vậy phải có đường dự phòng bằng textarea tạm, nếu không thì
 * nút sẽ im lặng không làm gì trên chính cái tình huống hay dùng nhất là
 * mở từ máy khác trong nhà.
 *
 * `onCopied` dùng để ghi nhận lần dùng. Nó được gọi sau khi copy thành công,
 * và lỗi của nó không ảnh hưởng tới việc copy.
 */

async function writeToClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Người dùng từ chối quyền, hoặc tab không được focus. Thử đường dự phòng.
    }
  }

  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    // Đặt ngoài khung nhìn để không làm trang nhảy khi focus
    textarea.style.position = "fixed";
    textarea.style.top = "-1000px";
    textarea.setAttribute("readonly", "");
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(textarea);
    return ok;
  } catch {
    return false;
  }
}

export function CopyButton({
  value,
  label = "Copy",
  confirmMessage,
  onCopied,
  className,
}: {
  value: string;
  label?: string;
  /** Khác null thì hỏi xác nhận trước khi copy. Dùng cho lệnh nguy hiểm. */
  confirmMessage?: string | null;
  onCopied?: () => void;
  className?: string;
}) {
  const [state, setState] = useState<"idle" | "done" | "failed">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Xoá timer khi component unmount, tránh setState trên component đã tháo
  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  async function handleClick() {
    if (confirmMessage && !window.confirm(confirmMessage)) return;

    const ok = await writeToClipboard(value);
    setState(ok ? "done" : "failed");

    if (ok) onCopied?.();

    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), 2000);
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-live="polite"
      className={
        className ??
        "shrink-0 rounded-md border border-[var(--color-border)] px-2 py-1 text-xs transition-colors hover:bg-[var(--color-surface-hover)]"
      }
    >
      {state === "done" ? "Đã copy" : state === "failed" ? "Không copy được" : label}
    </button>
  );
}
