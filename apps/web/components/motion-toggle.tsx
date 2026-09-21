"use client";

import { useEffect, useState, type ReactNode } from "react";

const STORAGE_KEY = "builder:diagram-motion";
const REDUCED_QUERY = "(prefers-reduced-motion: reduce)";

type Mode = "on" | "off";

/**
 * Bọc các sơ đồ và cho phép bật tắt hiệu ứng.
 *
 * Thứ tự ưu tiên, từ thấp lên cao:
 *   1. Mặc định: bật.
 *   2. Hệ điều hành khai báo giảm chuyển động: tắt.
 *   3. Người dùng tự bấm công tắc: cái này thắng cả hai trên.
 *
 * Trước khi JS chạy, component KHÔNG đặt attribute `data-motion`. Nhờ vậy CSS
 * tự quyết định: người bật giảm chuyển động ở hệ điều hành sẽ không thấy
 * animation nhấp nháy một khung hình rồi mới bị tắt.
 */
export function MotionToggle({ children }: { children: ReactNode }) {
  /** null nghĩa là chưa có lựa chọn tường minh, để CSS tự xử. */
  const [choice, setChoice] = useState<Mode | null>(null);
  const [osReduced, setOsReduced] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const reduced = window.matchMedia(REDUCED_QUERY).matches;
    setOsReduced(reduced);

    let saved: string | null = null;
    try {
      saved = localStorage.getItem(STORAGE_KEY);
    } catch {
      // localStorage bị chặn thì bỏ qua, dùng mặc định
    }
    if (saved === "on" || saved === "off") {
      setChoice(saved);
    }

    setLoaded(true);
  }, []);

  // Trạng thái đang thực sự áp dụng, dùng để hiện nhãn nút cho đúng
  const effective: Mode = choice ?? (osReduced ? "off" : "on");

  function toggle() {
    const next: Mode = effective === "on" ? "off" : "on";
    setChoice(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // không lưu được thì vẫn đổi trong phiên này
    }
  }

  return (
    <div
      // Chỉ đặt attribute khi người dùng đã chọn tường minh
      data-motion={choice ?? undefined}
      className="flex flex-col gap-6"
    >
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-[var(--color-ink-muted)]">
            Nét chạy trên mũi tên cho thấy hướng dữ liệu di chuyển. Sơ đồ 2 vẽ
            dần từng bước theo đúng thứ tự request.
          </p>

          <button
            type="button"
            onClick={toggle}
            aria-pressed={effective === "on"}
            className="shrink-0 rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs transition-colors hover:bg-[var(--color-surface-hover)]"
          >
            {effective === "on" ? "Tắt hiệu ứng" : "Bật hiệu ứng"}
          </button>
        </div>

        {/* Chỉ nhắc sau khi đã đọc được cấu hình, tránh nhấp nháy lúc tải */}
        {loaded && osReduced && effective === "off" ? (
          <p className="mt-2 rounded-md border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10 px-3 py-2 text-xs text-[var(--color-warn)]">
            Máy bạn đang bật chế độ giảm chuyển động, nên hiệu ứng bị tắt theo.
            Trên Windows đó là Settings → Accessibility → Visual effects →
            Animation effects. Muốn xem hiệu ứng mà không đổi cấu hình hệ điều
            hành thì bấm <strong>Bật hiệu ứng</strong>.
          </p>
        ) : null}

        {loaded && osReduced && effective === "on" ? (
          <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
            Đang bật thủ công, ghi đè cấu hình giảm chuyển động của hệ điều hành.
          </p>
        ) : null}
      </div>

      {children}
    </div>
  );
}
