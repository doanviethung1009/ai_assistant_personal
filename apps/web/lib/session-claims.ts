/**
 * MỘT tiêu chí "có phiên hợp lệ" cho cả middleware và getSessionUser (lib/session.ts). Thuần, không
 * "server-only" để middleware import được. Hai nơi dùng tiêu chí khác nhau sẽ gây vòng lặp: cookie
 * đúng chữ ký nhưng sai dạng (vd. phiên cũ thiếu `sv`) bị middleware coi là đã đăng nhập (/login → "/")
 * còn trang coi là chưa (→ /login).
 */
export interface SessionUser {
  uid: string;
  sv: number;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function parseSessionClaims(raw: { uid?: unknown; sv?: unknown } | null | undefined): SessionUser | null {
  const uid = raw?.uid;
  const sv = raw?.sv;
  if (typeof uid !== "string" || !UUID_RE.test(uid)) return null;
  if (typeof sv !== "number" || !Number.isInteger(sv) || sv < 0) return null;
  return { uid, sv };
}
