/** Các mốc nhanh của bộ lọc thời gian ở dashboard tham dự dự án. */
export const PERIOD_RANGES = [
  { id: "all", label: "Mọi thời gian", days: null },
  { id: "7d", label: "7 ngày gần đây", days: 7 },
  { id: "30d", label: "30 ngày gần đây", days: 30 },
  { id: "90d", label: "90 ngày gần đây", days: 90 },
  { id: "custom", label: "Tuỳ chọn khoảng ngày", days: null },
] as const;

export type PeriodRangeId = (typeof PERIOD_RANGES)[number]["id"];

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** YYYY-MM-DD hợp lệ thật (loại 2026-02-31), nếu không thì undefined. */
function parseDay(value: string | undefined): string | undefined {
  if (!value || !ISO_DAY.test(value)) return undefined;
  const d = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== value ? undefined : value;
}

/** Cộng/trừ ngày trên chuỗi ngày thuần, không đi qua múi giờ nên không lệch ở ranh giới DST. */
export function addDays(day: string, delta: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
}

export interface ResolvedPeriod {
  range: PeriodRangeId;
  /** Ngày bắt đầu/kết thúc (gồm cả ngày cuối) gửi cho API; undefined = không giới hạn. */
  from?: string;
  to?: string;
}

/**
 * Đổi tham số URL thành khoảng ngày địa phương.
 *
 * `range` thắng `from`/`to`: chỉ khi range = "custom" mới dùng hai ngày tự nhập, nếu không
 * đổi mốc nhanh sẽ vô tình giữ ngày cũ trong ô nhập. Mốc "N ngày gần đây" gồm cả hôm nay nên
 * bắt đầu từ today - (N - 1). Khoảng tự nhập bị đảo đầu/cuối thì đổi chỗ thay vì báo lỗi.
 */
export function resolvePeriod(
  range: string | undefined,
  from: string | undefined,
  to: string | undefined,
  today: string,
): ResolvedPeriod {
  const preset = PERIOD_RANGES.find((r) => r.id === range);
  if (preset?.days) {
    return { range: preset.id, from: addDays(today, -(preset.days - 1)), to: today };
  }
  if (preset?.id === "custom") {
    let a = parseDay(from);
    let b = parseDay(to);
    if (a && b && a > b) [a, b] = [b, a];
    return { range: "custom", from: a, to: b };
  }
  return { range: "all" };
}
