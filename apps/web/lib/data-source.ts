/**
 * Chế độ dữ liệu đọc LÚC CHẠY từ env, dùng cho middleware và auth (không "server-only" để
 * middleware import được). Logic phải khớp resolveDataSource() trong lib/store/types.ts.
 */
export function isApiMode(env: Readonly<Record<string, string | undefined>> = process.env): boolean {
  const raw = env.DATA_SOURCE?.trim().toLowerCase();
  if (raw === "api") return true;
  if (raw === "file" || raw === "memory") return false;
  // Tương thích ngược: DEMO_MODE=1 là memory. Mặc định (không đặt) là api.
  return env.DEMO_MODE !== "1";
}
