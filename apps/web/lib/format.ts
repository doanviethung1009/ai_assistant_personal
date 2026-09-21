// Timezone được cố định tường minh để server render và client hydrate ra
// cùng một chuỗi. Nếu để mặc định, server container và browser có thể lệch
// múi giờ và React sẽ báo hydration mismatch.
export const DISPLAY_TZ =
  process.env.NEXT_PUBLIC_DISPLAY_TZ ?? "Asia/Ho_Chi_Minh";

const LOCALE = "vi-VN";

const dateTimeFormatter = new Intl.DateTimeFormat(LOCALE, {
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: DISPLAY_TZ,
});

const dateFormatter = new Intl.DateTimeFormat(LOCALE, {
  weekday: "short",
  day: "2-digit",
  month: "2-digit",
  timeZone: DISPLAY_TZ,
});

const fullDateFormatter = new Intl.DateTimeFormat(LOCALE, {
  weekday: "long",
  day: "2-digit",
  month: "long",
  year: "numeric",
  timeZone: DISPLAY_TZ,
});

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return dateTimeFormatter.format(new Date(iso));
}

/** scheduled_for là date thuần (YYYY-MM-DD), không có giờ và không có timezone. */
export function formatPlainDate(value: string | null): string {
  if (!value) return "—";
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  return dateFormatter.format(new Date(Date.UTC(year, month - 1, day, 12)));
}

export function formatFullPlainDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  return fullDateFormatter.format(new Date(Date.UTC(year, month - 1, day, 12)));
}

export function formatMinutes(minutes: number | null): string {
  if (!minutes || minutes <= 0) return "—";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest}p`;
  if (rest === 0) return `${hours}h`;
  return `${hours}h${rest.toString().padStart(2, "0")}`;
}

/** Ngày hôm nay theo timezone hiển thị, dạng YYYY-MM-DD. */
export function todayInDisplayTz(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: DISPLAY_TZ,
  }).format(new Date());
  return parts;
}
