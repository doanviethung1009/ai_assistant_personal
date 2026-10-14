/**
 * Logic của callbacks.jwt (auth.ts), tách ra để test được.
 *
 * Auth.js cho client gọi POST /api/auth/session kèm `data`; nó chuyển dữ liệu đó vào callback jwt
 * với trigger "update" (xác minh trong @auth/core actions/session.js). Nếu callback gộp dữ liệu này
 * vào token thì client tự nâng được uid/sv. Vì vậy: lần đăng nhập chép uid/sv từ `user` (do
 * signIn gắn, từ core); mọi lần sau CHỈ giữ uid/sv đã có trong token, bỏ qua `session` và trigger.
 */
export interface SessionTokenClaims {
  [key: string]: unknown;
  uid?: string;
  sv?: number;
}

export function nextSessionToken(args: {
  token: SessionTokenClaims;
  user?: { uid?: string; sv?: number };
  trigger?: string;
  /** Dữ liệu client gửi khi trigger = "update": KHÔNG TIN, cố ý không đọc. */
  session?: unknown;
}): SessionTokenClaims {
  const { token, user, trigger } = args;
  if (trigger !== "update" && user?.uid !== undefined && user.sv !== undefined) {
    return { uid: user.uid, sv: user.sv };
  }
  return { uid: token.uid, sv: token.sv };
}
