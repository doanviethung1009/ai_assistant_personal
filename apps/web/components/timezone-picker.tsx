"use client";

import { useMemo, useState, useTransition } from "react";

import { setDisplayTimezoneAction } from "@/app/actions-user";
import { isValidTimezone, todayInDisplayTz } from "@/lib/format";
import type { DisplayTimezoneRead, TimezoneOption } from "@/lib/types";

function offsetLabel(minutes: number): string {
  const sign = minutes < 0 ? "-" : "+";
  const abs = Math.abs(minutes);
  const hh = String(Math.floor(abs / 60)).padStart(2, "0");
  const mm = String(abs % 60).padStart(2, "0");
  return `UTC${sign}${hh}:${mm}`;
}

/**
 * Chọn múi giờ hiển thị cho toàn hệ thống (một người dùng, cài đặt toàn cục).
 *
 * Đổi múi giờ làm "hôm nay" dịch ngay (task xong hôm nay, phút đã log, tiêu đề trang Hôm nay),
 * còn `scheduled_for` là ngày thuần nên KHÔNG dịch theo. Vì vậy hiện sẵn "Hôm nay theo múi giờ
 * này" trước khi lưu để người dùng thấy hệ quả. Lỗi hiện tại chỗ, không dùng alert.
 */
export function TimezonePicker({
  current,
  options,
}: {
  current: DisplayTimezoneRead;
  options: TimezoneOption[];
}) {
  const [value, setValue] = useState(current.timezone);
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);

  const offsets = useMemo(
    () => new Map(options.map((o) => [o.name, o.utc_offset_minutes])),
    [options],
  );

  const typed = value.trim();
  const valid = typed.length > 0 && typed.length <= 64 && isValidTimezone(typed);
  const offset = offsets.get(typed);

  function save(tz: string | null) {
    setMessage(null);
    startTransition(async () => {
      try {
        const result = await setDisplayTimezoneAction(tz);
        if (result.ok) {
          if (tz === null) setValue(current.default);
          setMessage({ text: "Đã lưu múi giờ.", ok: true });
        } else {
          setMessage({ text: result.error ?? "Không lưu được", ok: false });
        }
      } catch {
        setMessage({ text: "Không gọi được máy chủ", ok: false });
      }
    });
  }

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4">
      <h2 className="text-sm font-semibold">Múi giờ hiển thị</h2>
      <p className="mt-1 mb-4 text-xs text-[var(--color-ink-muted)]">
        Dùng để hiện giờ, tính &quot;hôm nay&quot; và xét quá hạn. Hiện đang dùng{" "}
        <strong>{current.timezone}</strong>{" "}
        ({current.source === "setting" ? "bạn đã chọn" : "mặc định của hệ thống"}). Đổi múi giờ
        làm &quot;hôm nay&quot; dịch theo ngay; ngày &quot;Dự định&quot; của task là ngày thuần
        nên không đổi.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) save(typed);
        }}
        className="flex flex-col gap-3"
      >
        <div>
          <label htmlFor="tz-input" className="sr-only">
            Tên múi giờ IANA
          </label>
          <input
            id="tz-input"
            type="text"
            list="tz-options"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="VD: Asia/Ho_Chi_Minh"
            autoComplete="off"
            spellCheck={false}
            aria-invalid={typed.length > 0 && !valid}
            className="w-full max-w-sm rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm"
          />
          <datalist id="tz-options">
            {options.map((o) => (
              <option key={o.name} value={o.name}>
                {offsetLabel(o.utc_offset_minutes)}
              </option>
            ))}
          </datalist>
          <p className="mt-2 text-xs text-[var(--color-ink-muted)]" aria-live="polite">
            {valid ? (
              <>
                {offset !== undefined ? `${offsetLabel(offset)} · ` : ""}
                Hôm nay theo múi giờ này: <strong>{todayInDisplayTz(typed)}</strong>
              </>
            ) : typed.length > 0 ? (
              "Chưa phải tên múi giờ hợp lệ (cần tên IANA, ví dụ Asia/Ho_Chi_Minh)."
            ) : (
              "Nhập tên múi giờ IANA."
            )}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={pending || !valid}
            className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {pending ? "Đang lưu..." : "Lưu múi giờ"}
          </button>
          <button
            type="button"
            disabled={pending || current.source === "default"}
            onClick={() => save(null)}
            className="rounded-md border border-[var(--color-border)] px-4 py-2 text-sm disabled:opacity-50"
          >
            Dùng mặc định ({current.default})
          </button>
          {message && (
            <span
              role={message.ok ? "status" : "alert"}
              className={`text-sm ${message.ok ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}
            >
              {message.text}
            </span>
          )}
        </div>
      </form>
    </section>
  );
}
