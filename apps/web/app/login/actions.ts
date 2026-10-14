"use server";

import { redirect } from "next/navigation";

import { signIn, signOut } from "@/auth";
import { authEnabled, readAuthConfig } from "@/lib/auth-config";
import { safeCallbackPath } from "@/lib/redirect-safety";

/**
 * Bắt đầu đăng nhập Google. Miễn trừ duy nhất khỏi guard "requireSession" của Server Action
 * (chưa có phiên là đúng). callbackUrl đến từ form nên LUÔN lọc lại ở đây, không tin client.
 */
export async function loginWithGoogleAction(formData: FormData): Promise<void> {
  if (!authEnabled()) redirect("/");
  const cfg = readAuthConfig();
  if (!cfg.ok) redirect("/config-error");
  const raw = formData.get("callbackUrl");
  const redirectTo = safeCallbackPath(typeof raw === "string" ? raw : null, cfg.authUrl);
  await signIn("google", { redirectTo });
}

/** Đăng xuất: chỉ xoá cookie phiên của trình duyệt này (Q9: không tăng session_version ở core). */
export async function logoutAction(): Promise<void> {
  if (!authEnabled()) redirect("/");
  await signOut({ redirectTo: "/login" });
}
