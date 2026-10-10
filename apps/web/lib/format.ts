// Múi giờ hiển thị KHÔNG còn là hằng số: người dùng đổi được lúc chạy (cài đặt
// `display_timezone`). Mọi hàm ở đây nhận `tz` tường minh. Server render và client
// hydrate phải nhận CÙNG một chuỗi tz (qua TimezoneProvider) để không lệch hydration.
// Biến môi trường NEXT_PUBLIC cũ về múi giờ chỉ còn là giá trị dự phòng trong lib/api.ts khi API sập.

const LOCALE = "vi-VN";

// Tạo Intl.DateTimeFormat khá tốn, nên cache theo (kiểu, tz).
const formatterCache = new Map<string, Intl.DateTimeFormat>();

function formatter(
  kind: string,
  tz: string,
  options: Intl.DateTimeFormatOptions,
  locale: string = LOCALE,
): Intl.DateTimeFormat {
  const key = `${kind}|${tz}`;
  let found = formatterCache.get(key);
  if (!found) {
    found = new Intl.DateTimeFormat(locale, { ...options, timeZone: tz });
    formatterCache.set(key, found);
  }
  return found;
}

export function formatDateTime(iso: string | null, tz: string): string {
  if (!iso) return "—";
  return formatter("datetime", tz, {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

/** scheduled_for là date thuần (YYYY-MM-DD), không có giờ và không có timezone. */
export function formatPlainDate(value: string | null, tz: string): string {
  if (!value) return "—";
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  // Ngày thuần dựng ở 12:00 UTC rồi format bằng chính `tz`: giữa trưa UTC nằm trong cùng
  // ngày lịch với mọi offset từ -12 tới +11, riêng +12..+14 có thể nhảy sang ngày kế. Để
  // chắc chắn, format theo UTC (ngày thuần không thuộc múi giờ nào) và bỏ qua `tz`.
  void tz;
  return formatter("plain-date-utc", "UTC", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
  }).format(new Date(Date.UTC(year, month - 1, day, 12)));
}

export function formatFullPlainDate(value: string, tz: string): string {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  void tz; // xem formatPlainDate: ngày thuần format theo UTC
  return formatter("full-date-utc", "UTC", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(new Date(Date.UTC(year, month - 1, day, 12)));
}

/**
 * Hạn của task. Hạn "cả ngày" (Jira duedate) lưu 00:00 UTC của ngày lịch, nên ngày hiển thị
 * là `due_at.slice(0, 10)`, KHÔNG quy đổi múi giờ (quy đổi sẽ lệch ngày ở múi giờ âm).
 */
export function formatDue(
  task: { due_at: string | null; due_all_day: boolean },
  tz: string,
): string {
  if (!task.due_at) return "—";
  if (task.due_all_day) return formatPlainDate(task.due_at.slice(0, 10), tz);
  return formatDateTime(task.due_at, tz);
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
export function todayInDisplayTz(tz: string): string {
  return formatter(
    "today",
    tz,
    { year: "numeric", month: "2-digit", day: "2-digit" },
    "en-CA",
  ).format(new Date());
}

/** Ngày (YYYY-MM-DD) của một thời điểm theo `tz`. */
export function dayInTz(iso: string, tz: string): string {
  return formatter(
    "day",
    tz,
    { year: "numeric", month: "2-digit", day: "2-digit" },
    "en-CA",
  ).format(new Date(iso));
}

/** Offset (phút, dương = đi trước UTC) của `tz` tại thời điểm `at`. */
export function tzOffsetMinutes(tz: string, at: Date): number {
  const parts = formatter(
    "offset",
    tz,
    {
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    },
    "en-US",
  ).formatToParts(at);
  const get = (type: string) =>
    Number(parts.find((p) => p.type === type)?.value ?? "0");
  const asUtc = Date.UTC(
    get("year"),
    get("month") - 1,
    get("day"),
    get("hour") % 24,
    get("minute"),
    get("second"),
  );
  // Bỏ phần mili giây của `at` để hiệu số là bội số của phút.
  return Math.round((asUtc - Math.floor(at.getTime() / 1000) * 1000) / 60_000);
}

/**
 * Đổi chuỗi `datetime-local` ("YYYY-MM-DDTHH:mm") hiểu theo múi giờ `tz` sang ISO UTC.
 * Thay cho `new Date(local)` vốn dùng múi giờ của BROWSER (sai khi browser khác múi giờ
 * đã chọn). Lặp hai lần để xử lý đúng ranh giới DST. Trả chuỗi rỗng nếu đầu vào sai.
 */
export function zonedLocalToUtcIso(local: string, tz: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(local);
  if (!match) return "";
  const [, y, mo, d, h, mi, s] = match;
  const wallAsUtc = Date.UTC(
    Number(y),
    Number(mo) - 1,
    Number(d),
    Number(h),
    Number(mi),
    Number(s ?? "0"),
  );
  let guess = wallAsUtc - tzOffsetMinutes(tz, new Date(wallAsUtc)) * 60_000;
  guess = wallAsUtc - tzOffsetMinutes(tz, new Date(guess)) * 60_000;
  const result = new Date(guess);
  return Number.isNaN(result.getTime()) ? "" : result.toISOString();
}

/** Tên IANA có dùng được với Intl không (dùng ở engine chế độ file và Server Action). */
export function isValidTimezone(tz: string): boolean {
  try {
    new Intl.DateTimeFormat("en", { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}
