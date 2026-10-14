import { headers } from "next/headers";
import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

import { readAuthConfig } from "@/lib/auth-config";
import { clientIpFrom } from "@/lib/client-ip";
import { nextSessionToken } from "@/lib/session-token";
import { safeCallbackPath } from "@/lib/redirect-safety";

/**
 * Auth.js v5: đăng nhập Google, invite-only qua core. Phiên là cookie JWE (không adapter) chỉ chứa
 * `uid` và `sv`. Mỗi lời gọi core web tự ký JWT 60 giây riêng (lib/core-jwt.ts).
 *
 * Cấu hình LƯỜI (hàm, không object): import file này không ném lỗi khi thiếu AUTH_* (DATA_SOURCE=file,
 * hoặc `next build` không có secret). Hàm chỉ chạy khi Auth.js thật sự được gọi, và nơi gọi
 * (middleware, lib/session.ts) đã kiểm cấu hình + chế độ api trước.
 */

const LOGIN_ERRORS_FROM_CORE = new Set([
  "not_invited",
  "disabled",
  "email_unverified",
  "hd_not_allowed",
  "account_mismatch",
]);

/** Claim Google là dữ liệu không tin cậy: cắt độ dài trước khi gửi core. */
function clip(value: unknown, max: number): string | undefined {
  return typeof value === "string" && value ? value.slice(0, max) : undefined;
}

export const { handlers, auth, signIn, signOut } = NextAuth(() => {
  const cfg = readAuthConfig();
  if (!cfg.ok) {
    // Chỉ tên biến, không giá trị.
    throw new Error(`Thiếu cấu hình auth: ${cfg.missing.join(", ")}`);
  }

  return {
    secret: cfg.authSecret,
    trustHost: true,
    useSecureCookies: cfg.secureCookies,
    debug: false,
    pages: { signIn: "/login", error: "/login" },
    providers: [
      Google({
        clientId: cfg.googleId,
        clientSecret: cfg.googleSecret,
        // Không xin access_type=offline: không lưu refresh token Google, không gọi Google API sau đăng nhập.
        authorization: {
          params: {
            prompt: "select_account",
            scope: "openid email profile",
            // `hd` chỉ gợi ý UI của Google; kiểm thật nằm ở callback signIn và ở core.
            ...(cfg.allowedHd.length === 1 ? { hd: cfg.allowedHd[0] } : {}),
          },
        },
      }),
    ],
    session: { strategy: "jwt", maxAge: 7 * 24 * 60 * 60, updateAge: 24 * 60 * 60 },
    // Không log token/session/profile: chỉ tên lỗi.
    logger: {
      error: (error: Error) => console.error("[auth] lỗi:", error.name),
      warn: () => undefined,
      debug: () => undefined,
    },
    callbacks: {
      async signIn({ user, profile }) {
        if (!profile || typeof profile.sub !== "string" || typeof profile.email !== "string") {
          return "/login?error=denied";
        }
        if (profile.email_verified !== true) return "/login?error=email_unverified";
        const hd = typeof profile.hd === "string" ? profile.hd.toLowerCase() : undefined;
        if (cfg.allowedHd.length > 0 && (!hd || !cfg.allowedHd.includes(hd))) {
          return "/login?error=hd_not_allowed";
        }

        // Import lười: lib/api import lib/session import auth.ts (vòng), nên chỉ nạp khi cần.
        const { coreLogin, coreProbeMe } = await import("@/lib/api");
        const { CoreApiError } = await import("@/lib/core-errors");
        let uid: string;
        let sv: number;
        try {
          let ip: string | null = null;
          try {
            ip = clientIpFrom(await headers());
          } catch {
            ip = null; // ngoài request context
          }
          const result = await coreLogin(
            {
              google_sub: profile.sub.slice(0, 255),
              email: profile.email.slice(0, 320),
              email_verified: true,
              name: clip(profile.name, 200),
              hd: clip(hd, 255),
            },
            ip,
          );
          uid = result.user_id;
          sv = result.session_version;
        } catch (error) {
          if (error instanceof CoreApiError) {
            if (error.status === 403) {
              const code = error.code && LOGIN_ERRORS_FROM_CORE.has(error.code) ? error.code : "denied";
              return `/login?error=${code}`;
            }
            if (error.status === 429) return "/login?error=rate_limited";
          }
          return "/login?error=unavailable";
        }

        // Tự kiểm khoá chung: nếu CORE_JWT_SECRET của web lệch core thì dừng ở đây, không để
        // người dùng lặp vô hạn login → expired → login.
        try {
          await coreProbeMe({ uid, sv });
        } catch (error) {
          if (error instanceof CoreApiError && error.status === 401 && error.code === "token_invalid") {
            return "/login?error=config";
          }
          return "/login?error=unavailable";
        }

        user.uid = uid;
        user.sv = sv;
        return true;
      },
      // Cookie chỉ chứa uid + sv (không chép name/email/picture mặc định của Auth.js).
      // trigger "update" (client POST /api/auth/session) không được đổi token: xem lib/session-token.ts.
      jwt({ token, user, trigger, session }) {
        return nextSessionToken({ token, user, trigger, session });
      },
      // Spec 4.3 chỉ cho lộ `{ uid }`, nhưng `sv` PHẢI có phía server: nó nằm trong khoá cache `uid:sv`
      // (thu hồi phiên ra khoá mới) và trong JWT web→core. Lấy từ token qua getToken() phải tự dựng lại
      // tên cookie/salt/chunk, thêm một đường giải mã song song; session callback là chỗ ít rủi ro nhất.
      // Chỉ trình duyệt của chính người đó thấy được (qua /api/auth/session), và sv không phải bí mật.
      session({ session, token }) {
        return { expires: session.expires, uid: token.uid, sv: token.sv };
      },
      redirect({ url, baseUrl }) {
        return new URL(safeCallbackPath(url, baseUrl), baseUrl).toString();
      },
    },
  };
});
