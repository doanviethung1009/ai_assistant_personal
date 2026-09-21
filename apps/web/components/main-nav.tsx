"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  PRIMARY_NAV,
  SECONDARY_NAV,
  isItemActive,
  type NavItem,
} from "@/lib/nav";

/**
 * Nav phẳng hai cấp, mọi mục hiện sẵn.
 *
 * Client component vì cần `usePathname` để tô mục đang mở. Không có state nào
 * khác, không dropdown, nên cũng không có gì để đóng mở hay bắt sự kiện ngoài.
 */
export function MainNav() {
  const pathname = usePathname();

  return (
    // items-end để hai dòng thẳng lề phải với nhau trên desktop
    <nav aria-label="Điều hướng chính" className="flex flex-col gap-2 sm:items-end">
      {/* ── Cấp 1: việc hàng ngày ─────────────────────────────────── */}
      <ul className="flex flex-wrap items-center gap-1">
        {PRIMARY_NAV.map((item) => (
          <li key={item.href}>
            <PrimaryLink item={item} pathname={pathname} />
          </li>
        ))}
      </ul>

      {/* ── Cấp 2: tài liệu về dự án ──────────────────────────────── */}
      <ul className="flex flex-wrap items-center gap-x-1 gap-y-0.5">
        {SECONDARY_NAV.map((item, index) => (
          <li key={item.href} className="flex items-center">
            {index > 0 ? (
              <span
                aria-hidden="true"
                className="px-1 text-[10px] text-[var(--color-border)]"
              >
                ·
              </span>
            ) : null}
            <SecondaryLink item={item} pathname={pathname} />
          </li>
        ))}
      </ul>
    </nav>
  );
}

function PrimaryLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const active = isItemActive(item.href, pathname);

  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={`block rounded-md px-3 py-1.5 text-sm transition-colors ${active
        ? "bg-[var(--color-accent)]/15 font-medium text-[var(--color-ink)] ring-1 ring-inset ring-[var(--color-accent)]/40"
        : "text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink)]"
        }`}
    >
      {/* Nhãn ngắn dưới 400px để bốn mục vẫn nằm trên một dòng */}
      <span className="hidden min-[400px]:inline">{item.label}</span>
      <span className="min-[400px]:hidden">{item.short ?? item.label}</span>
    </Link>
  );
}

function SecondaryLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const active = isItemActive(item.href, pathname);

  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={`rounded px-1.5 py-0.5 text-xs transition-colors ${active
        ? "font-medium text-[var(--color-accent)] underline decoration-[var(--color-accent)]/50 underline-offset-2"
        : "text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
        }`}
    >
      {item.label}
    </Link>
  );
}
