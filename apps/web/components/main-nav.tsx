"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PRIMARY_NAV, SECONDARY_NAV, AI_NAV, isItemActive, type NavItem } from "@/lib/nav";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

export function MainNav() {
  const pathname = usePathname();

  return (
    <nav aria-label="Điều hướng chính" className="flex flex-col gap-6 px-4 py-6">
      <CollapsibleSection title="Hàng ngày" defaultOpen={true}>
        {PRIMARY_NAV.map((item) => (
          <li key={item.href}>
            <PrimaryLink item={item} pathname={pathname} />
          </li>
        ))}
      </CollapsibleSection>

      <CollapsibleSection title="Hệ sinh thái AI" defaultOpen={true}>
        {AI_NAV.map((item) => (
          <li key={item.href}>
            <SecondaryLink item={item} pathname={pathname} />
          </li>
        ))}
      </CollapsibleSection>

      <CollapsibleSection title="Tài liệu & Hệ thống" defaultOpen={false}>
        {SECONDARY_NAV.map((item) => (
          <li key={item.href}>
            <SecondaryLink item={item} pathname={pathname} />
          </li>
        ))}
      </CollapsibleSection>
    </nav>
  );
}

function CollapsibleSection({ title, children, defaultOpen }: { title: string, children: React.ReactNode, defaultOpen: boolean }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  return (
    <div>
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between px-3 mb-2 text-[10px] font-bold uppercase tracking-wider text-[var(--color-ink-muted)] opacity-70 hover:opacity-100 transition-opacity"
      >
        <span>{title}</span>
        {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
      </button>
      {isOpen && (
        <ul className="flex flex-col gap-1.5 animate-in slide-in-from-top-2 fade-in duration-200">
          {children}
        </ul>
      )}
    </div>
  );
}

function PrimaryLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const active = isItemActive(item.href, pathname);
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={`group flex items-center gap-3.5 rounded-xl px-3 py-2.5 text-sm transition-all duration-300 ${active
        ? "bg-gradient-to-r from-[var(--color-accent)] to-blue-600 shadow-md shadow-blue-500/20 text-white font-semibold"
        : "text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink)]"
        }`}
    >
      <Icon
        className={`size-5 shrink-0 transition-transform duration-300 ${active ? "text-white scale-110" : "text-[var(--color-ink-muted)] group-hover:text-[var(--color-ink)] group-hover:scale-110"}`}
      />
      <span>{item.label}</span>
    </Link>
  );
}

function SecondaryLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const active = isItemActive(item.href, pathname);
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={`group flex items-center gap-3.5 rounded-xl px-3 py-2 text-xs transition-all duration-300 ${active
        ? "bg-[var(--color-accent)]/10 font-bold text-[var(--color-accent)]"
        : "text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink)]"
        }`}
    >
      <Icon
        className={`size-4 shrink-0 transition-transform duration-300 ${active ? "text-[var(--color-accent)] scale-110" : "text-[var(--color-ink-muted)] group-hover:text-[var(--color-ink)] group-hover:scale-110"}`}
      />
      <span>{item.label}</span>
    </Link>
  );
}
