import type { Metadata } from "next";
import Link from "next/link";

import { MainNav } from "@/components/main-nav";
import { DATA_SOURCE } from "@/lib/api";

import "./globals.css";

export const metadata: Metadata = {
  title: "Builder AI Assistant",
  description: "Quản lý công việc cá nhân, theo dõi task hàng ngày",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body className="min-h-screen antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-[var(--color-accent)] focus:px-3 focus:py-2 focus:text-white"
        >
          Bỏ qua điều hướng
        </a>

        <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-4 sm:px-6">
          <header className="flex flex-col gap-4 border-b border-[var(--color-border)] py-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-lg font-semibold tracking-tight">
                Builder AI Assistant
              </p>
              <p className="text-sm text-[var(--color-ink-muted)]">
                Phase 1 — task store cá nhân
              </p>
            </div>

            <MainNav />
          </header>

          {DATA_SOURCE === "memory" ? (
            <p
              role="status"
              className="mt-4 rounded-md border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10 px-3 py-2 text-xs text-[var(--color-warn)]"
            >
              Dữ liệu đang nằm trong bộ nhớ và sẽ mất khi dev server khởi động
              lại. Đặt <code>DATA_SOURCE=file</code> trong{" "}
              <code>apps/web/.env.local</code> để lưu xuống file JSON.
            </p>
          ) : null}

          {DATA_SOURCE === "file" ? (
            <p
              role="status"
              className="mt-4 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-2 text-xs text-[var(--color-ink-muted)]"
            >
              Đang lưu vào file JSON cục bộ, chưa dùng Postgres. Xem và backup
              ở trang <Link href="/data" className="text-[var(--color-accent)] underline">Dữ liệu</Link>.
            </p>
          ) : null}

          <main id="main" className="flex-1 py-6">
            {children}
          </main>

          <footer className="border-t border-[var(--color-border)] py-4 text-xs text-[var(--color-ink-muted)]">
            Nguồn dữ liệu hiện tại: nhập tay. Integration Jira, Calendar,
            Obsidian sẽ cắm vào cùng task store ở Phase 2.
          </footer>
        </div>
      </body>
    </html>
  );
}
