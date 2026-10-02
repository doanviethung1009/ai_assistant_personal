"use client";

import { useState, type ReactNode } from "react";

/**
 * Ẩn một khối thông tin "nội bộ nhưng không phải secret thật" sau một nút
 * bấm, mặc định ẩn.
 *
 * Phân biệt rõ với secret thật (API_KEY, DATABASE_URL, LITELLM_MASTER_KEY):
 * những giá trị đó KHÔNG BAO GIỜ được truyền tới component này hay bất kỳ
 * đâu trong bundle client — `lib/api.ts` có "server-only" và chỉ dùng chúng
 * để set header phía server (xem comment đầu file đó). Khối này chỉ che
 * thông tin kiểu "biết được thì hiểu thêm về cách hệ thống lắp ráp" (URL
 * nội bộ của core API, tên biến môi trường đang dùng) — không mật, nhưng
 * không có lý do để hiện sẵn ngay khi mở trang cho ai cũng thấy.
 *
 * Không lưu lựa chọn vào localStorage như MotionToggle: đây là thông tin
 * nhạy hơn một chút so với hiệu ứng hoạt hình, nên mỗi lần tải trang lại về
 * trạng thái ẩn mặc định, chủ ý.
 */
export function SensitiveToggle({
  label,
  children,
}: {
  /** Mô tả ngắn thứ sắp hiện, hiển thị cạnh nút bấm. */
  label: string;
  children: ReactNode;
}) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="rounded-md border border-dashed border-[var(--color-border)] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-[var(--color-ink-muted)]">{label}</p>
        <button
          type="button"
          onClick={() => setVisible((prev) => !prev)}
          aria-expanded={visible}
          className="shrink-0 rounded-md border border-[var(--color-border)] px-3 py-1 text-xs transition-colors hover:bg-[var(--color-surface-hover)]"
        >
          {visible ? "Ẩn" : "Hiện"}
        </button>
      </div>

      {visible ? <div className="mt-3">{children}</div> : null}
    </div>
  );
}
