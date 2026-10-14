import { NextResponse, type NextFetchEvent, type NextRequest } from "next/server";

import { auth } from "@/auth";
import { authEnabled, readAuthConfig } from "@/lib/auth-config";
import { parseSessionClaims } from "@/lib/session-claims";
import { safeCallbackPath } from "@/lib/redirect-safety";

/**
 * Lớp UX: chưa có phiên thì đưa về /login. KHÔNG kiểm quyền và KHÔNG gọi core (mỗi request đi
 * qua đây, một lời gọi mạng ở đây là chậm cho mọi trang). Ranh giới bảo mật thật nằm ở coreFetch
 * (không phiên thì không gọi core) và ở core (đòi JWT).
 *
 * Runtime nodejs: đọc process.env lúc chạy trong image standalone và dùng chung jose/net.
 * Chế độ file/memory: cho qua TRƯỚC khi chạm Auth.js (không có đăng nhập, mục 4.10).
 * Trang công khai duy nhất là /login (cùng /api/auth/*, /auth/expired, /config-error: loại ở matcher).
 *
 * Redirect dựng từ request.nextUrl (Next middleware đòi URL tuyệt đối, Location tương đối ném
 * ERR_INVALID_URL). Origin lấy từ Host của request, không từ bind 0.0.0.0 của container.
 */
function redirectTo(request: NextRequest, pathname: string, search = ""): NextResponse {
  const url = request.nextUrl.clone();
  url.pathname = pathname;
  url.search = search;
  return NextResponse.redirect(url, 302);
}

type MiddlewareFn = (request: NextRequest, event: NextFetchEvent) => Response | undefined | Promise<Response | undefined>;

/**
 * Với cấu hình lười, auth(handler) của Auth.js v5 trả về PROMISE của hàm middleware (không phải hàm),
 * dù kiểu khai báo nói ngược lại. Promise.resolve bọc cả hai dạng để không vỡ khi bản sau đổi.
 * Phải dùng wrapper này (không phải auth() trần) để cookie phiên được gia hạn trượt qua middleware.
 */
const guarded: Promise<MiddlewareFn> = Promise.resolve(auth((request) => {
  const { pathname, search } = request.nextUrl;
  const hasSession = parseSessionClaims(request.auth) !== null;

  if (pathname === "/login") {
    return hasSession ? redirectTo(request, "/") : NextResponse.next();
  }
  if (!hasSession) {
    const callback = safeCallbackPath(`${pathname}${search}`, process.env.AUTH_URL);
    return redirectTo(request, "/login", callback === "/" ? "" : `?callbackUrl=${encodeURIComponent(callback)}`);
  }
  return NextResponse.next();
}) as unknown as MiddlewareFn | Promise<MiddlewareFn>);

export default async function middleware(request: NextRequest, event: NextFetchEvent) {
  if (!authEnabled()) {
    return request.nextUrl.pathname === "/login" ? redirectTo(request, "/") : NextResponse.next();
  }
  if (!readAuthConfig().ok) {
    // Thiếu cấu hình: trang liệt kê TÊN biến thiếu, không gọi core, không mở cửa không đăng nhập.
    return NextResponse.rewrite(new URL("/config-error", request.url), { status: 503 });
  }
  return (await guarded)(request, event);
}

export const config = {
  runtime: "nodejs",
  // Chỉ bỏ qua các đuôi file TĨNH cụ thể. Không dùng ".*\\.ext$" tổng quát: nó sẽ cho mọi path có
  // đuôi (vd. /api/export.json, /anything.x) lọt qua không cần phiên.
  matcher: [
    "/((?!_next/|favicon\\.ico|api/auth/|auth/expired|config-error|.*\\.(?:png|jpe?g|gif|svg|ico|webp|avif|css|js|map|txt|woff2?|ttf)$).*)",
  ],
};
