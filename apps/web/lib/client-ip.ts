import { isIP } from "node:net";

/**
 * IP của browser để core giới hạn tốc độ đăng nhập (client_ip của /auth/login).
 *
 * ══════════════════════════════════════════════════════════════════════
 *  CHỈ BẬT TRUST_FORWARDED_FOR=true KHI web nằm SAU reverse proxy tin cậy và cổng 3000 KHÔNG
 *  được publish ra LAN (không dùng cùng chế độ LAN publish cổng 3000). Nếu client nối thẳng được
 *  vào web thì nó tự đặt X-Forwarded-For và né giới hạn đăng nhập tuỳ ý.
 * ══════════════════════════════════════════════════════════════════════
 *
 * Mỗi proxy tin cậy NỐI THÊM IP của bên nối tới nó vào cuối X-Forwarded-For; phần bên trái do
 * client (hoặc proxy ngoài) tự khai nên không tin được. Vì vậy lấy phần tử thứ `TRUSTED_PROXY_HOPS`
 * tính TỪ BÊN PHẢI (mặc định 1 = proxy duy nhất ngay trước web, phần tử cuối). Không đủ phần tử
 * hoặc không phải IP hợp lệ → null (core dùng IP kết nối). Không log IP cùng email.
 */
export function clientIpFrom(
  headers: { get(name: string): string | null },
  env: Readonly<Record<string, string | undefined>> = process.env,
): string | null {
  if (env.TRUST_FORWARDED_FOR !== "true") return null;
  const hops = Number.parseInt(env.TRUSTED_PROXY_HOPS ?? "1", 10);
  const n = Number.isInteger(hops) && hops >= 1 && hops <= 10 ? hops : 1;
  const parts = (headers.get("x-forwarded-for") ?? "").split(",").map((p) => p.trim());
  const candidate = parts[parts.length - n];
  if (!candidate || candidate.length > 45 || isIP(candidate) === 0) return null;
  return candidate;
}
