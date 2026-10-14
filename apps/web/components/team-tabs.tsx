import Link from "next/link";

const TABS = [
  { id: "list", href: "/team", label: "Danh sách task" },
  { id: "participation", href: "/team/participation", label: "Tham dự dự án" },
] as const;

/**
 * Thanh tab của khu Team. Mỗi tab là một route riêng (không phải state phía client) để
 * bộ lọc ở tab này không kéo theo việc tính lại số liệu của tab kia.
 */
export function TeamTabs({ active }: { active: (typeof TABS)[number]["id"] }) {
  return (
    <nav aria-label="Khu Team" className="flex gap-1 border-b border-[var(--color-border)]">
      {TABS.map((tab) => (
        <Link
          key={tab.id}
          href={tab.href}
          aria-current={tab.id === active ? "page" : undefined}
          className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
            tab.id === active
              ? "border-[var(--color-accent)] text-[var(--color-ink)]"
              : "border-transparent text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
          }`}
        >
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}
