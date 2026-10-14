import { NextResponse } from "next/server";

import { handlers } from "@/auth";
import { authEnabled, readAuthConfig } from "@/lib/auth-config";

export const dynamic = "force-dynamic";

/**
 * Route của Auth.js. Chỉ tồn tại ở DATA_SOURCE=api: file/memory không có đăng nhập nên 404
 * trước khi chạm Auth.js. Thiếu cấu hình → 503 (không để Auth.js ném lỗi thô).
 */
function guard(): Response | null {
  if (!authEnabled()) return new NextResponse(null, { status: 404 });
  if (!readAuthConfig().ok) return new NextResponse(null, { status: 503 });
  return null;
}

export async function GET(request: Request): Promise<Response> {
  return guard() ?? handlers.GET(request as Parameters<typeof handlers.GET>[0]);
}

export async function POST(request: Request): Promise<Response> {
  return guard() ?? handlers.POST(request as Parameters<typeof handlers.POST>[0]);
}
