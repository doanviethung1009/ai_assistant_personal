import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Suspense } from "react";
import { Menu } from "lucide-react";

import { MainNav } from "@/components/main-nav";
import { UserMenu, UserMenuSkeleton } from "@/components/user-menu";
import { DATA_SOURCE, DISPLAY_TZ, getMe } from "@/lib/api";
import { authEnabled } from "@/lib/auth-config";
import { classifyCoreError } from "@/lib/core-errors";
import { getSessionUser } from "@/lib/session";
import { TimezoneProvider } from "@/lib/timezone-context";
import { ChatAssistant } from "@/components/chat-assistant";

import "./globals.css";

export const metadata: Metadata = {
  title: "Builder AI Assistant",
  description: "Quản lý công việc cá nhân, theo dõi task hàng ngày",
};

// DISPLAY_TZ đọc biến TZ lúc chạy; không để Next prerender lúc build kẻo bake múi giờ của máy build.
export const dynamic = "force-dynamic";

/**
 * Khối người dùng ở sidebar. Nằm trong <Suspense> nên khung trang (nav, tiêu đề) hiện ngay, không
 * chờ GET /me. getMe bọc React.cache nên trang con dùng chung kết quả, không gọi core lần hai.
 * Chỉ token_invalid/user_inactive mới đăng xuất; core sập chỉ hiện dòng cảnh báo nhỏ.
 */
async function UserMenuLoader() {
  try {
    return <UserMenu me={await getMe()} />;
  } catch (error) {
    const kind = classifyCoreError(error);
    if (kind === "session_expired") redirect("/auth/expired");
    if (kind === "unauthenticated") redirect("/login");
    return (
      <p role="status" className="border-t border-[var(--color-border)] px-4 py-3 text-xs text-[var(--color-warn)]">
        Không kết nối được core
      </p>
    );
  }
}

/**
 * Nav lọc theo quyền. Fallback (trong lúc chờ /me hoặc khi core lỗi) là nav không có mục cần quyền,
 * nên khung hiện ngay. getMe dùng chung React.cache với UserMenuLoader và trang con: một lời gọi.
 */
async function NavLoader() {
  try {
    return <MainNav permissions={(await getMe()).permissions} />;
  } catch (error) {
    const kind = classifyCoreError(error);
    if (kind === "session_expired") redirect("/auth/expired");
    if (kind === "unauthenticated") redirect("/login");
    return <MainNav />;
  }
}

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // Chỉ giải mã cookie, không gọi core. api mà chưa có phiên (/login, /config-error): không nav, không gọi core.
  const loggedIn = authEnabled() ? (await getSessionUser()) !== null : false;
  const bare = authEnabled() && !loggedIn;
  if (bare) {
    return (
      <html lang="vi">
        <body className="h-screen overflow-y-auto bg-[var(--color-surface)] antialiased">{children}</body>
      </html>
    );
  }

  return (
    <html lang="vi">
      <body className="flex h-screen overflow-hidden bg-[var(--color-surface)] antialiased">
        <TimezoneProvider tz={DISPLAY_TZ}>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-[var(--color-accent)] focus:px-3 focus:py-2 focus:text-white"
        >
          Bỏ qua điều hướng
        </a>

        {/* ── Sidebar Desktop ────────────────────────────────────────── */}
        <aside className="hidden w-[272px] shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-surface-raised)]/30 sm:flex">
          <div className="flex h-[68px] shrink-0 items-center border-b border-[var(--color-border)] px-5">
            <div>
              <p className="text-sm font-semibold tracking-tight text-[var(--color-ink)]">
                Builder AI Assistant
              </p>
              <p className="text-xs text-[var(--color-ink-muted)]">
                Phase 1 — task store cá nhân
              </p>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {loggedIn ? (
              <Suspense fallback={<MainNav />}>
                <NavLoader />
              </Suspense>
            ) : (
              <MainNav permissions="all" />
            )}
          </div>
          {loggedIn ? (
            <Suspense fallback={<UserMenuSkeleton />}>
              <UserMenuLoader />
            </Suspense>
          ) : null}
        </aside>

        {/* ── Main Content Area ──────────────────────────────────────── */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Header Mobile */}
          <header className="flex h-14 shrink-0 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface-raised)] px-4 sm:hidden">
            <p className="text-sm font-semibold tracking-tight">
              Builder AI Assistant
            </p>
            {/* Tạm thời dùng icon Menu, sau này có thể làm sheet đóng/mở thật */}
            <button
              type="button"
              className="text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
              aria-label="Mở menu"
            >
              <Menu className="h-5 w-5" />
            </button>
          </header>

          <main id="main" className="flex-1 overflow-y-auto px-4 py-6 sm:px-8 sm:py-8 xl:px-12 xl:py-10">
            <div className="mx-auto max-w-[1680px]">
              {DATA_SOURCE === "memory" ? (
                <p
                  role="status"
                  className="mb-6 rounded-md border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10 px-3 py-2 text-xs text-[var(--color-warn)]"
                >
                  Dữ liệu đang nằm trong bộ nhớ và sẽ mất khi dev server khởi động
                  lại. Đặt <code>DATA_SOURCE=file</code> trong{" "}
                  <code>apps/web/.env.local</code> để lưu xuống file JSON.
                </p>
              ) : null}

              {DATA_SOURCE === "file" ? (
                <p
                  role="status"
                  className="mb-6 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-2 text-xs text-[var(--color-ink-muted)]"
                >
                  Đang lưu vào file JSON cục bộ, chưa dùng Postgres. Xem và backup
                  ở trang <Link href="/data" className="text-[var(--color-accent)] underline">Dữ liệu</Link>.
                  Chế độ này không có đăng nhập, không mở cho người khác truy cập.
                </p>
              ) : null}

              {children}
            </div>
          </main>

          <footer className="shrink-0 border-t border-[var(--color-border)] px-4 py-4 text-center text-xs text-[var(--color-ink-muted)] sm:px-8">
            Nguồn dữ liệu hiện tại: nhập tay. Integration Jira, Calendar, Obsidian
            sẽ cắm vào cùng task store ở Phase 2.
          </footer>
        </div>
        
        {/* Chat AI Assistant Layer */}
        <ChatAssistant />
        </TimezoneProvider>
      </body>
    </html>
  );
}
