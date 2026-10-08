import { ArrowRightToLine, Database, Download, FileJson, FileText, Key } from "lucide-react";

const EXPORTS = [
  {
    href: "/api/export?format=json",
    title: "JSON Toàn bộ Dữ liệu",
    note: "Backup Project, Task, Sổ tay kèm tags và nhật ký thay đổi.",
    icon: Database,
    color: "from-blue-500/20 to-cyan-500/20 text-blue-600",
  },
  {
    href: "/api/export?format=json&entity=vault",
    title: "JSON Két bảo mật",
    note: "Bản sao lưu Két bảo mật mã hoá.",
    icon: Key,
    color: "from-amber-500/20 to-orange-500/20 text-amber-600",
  },
  {
    href: "/api/export?format=csv&entity=tasks",
    title: "CSV Danh sách Task",
    note: "Mở được bằng Excel, không có nhật ký.",
    icon: FileJson,
    color: "from-emerald-500/20 to-teal-500/20 text-emerald-600",
  },
  {
    href: "/api/export?format=csv&entity=projects",
    title: "CSV Dự án",
    note: "Danh sách project kèm mã và màu.",
    icon: FileJson,
    color: "from-indigo-500/20 to-blue-500/20 text-indigo-600",
  },
  {
    href: "/api/export?format=csv&entity=notes",
    title: "CSV Sổ tay",
    note: "Câu lệnh và SQL.",
    icon: FileText,
    color: "from-rose-500/20 to-red-500/20 text-rose-600",
  },
];


/** Lưới thẻ tải về. Mỗi thẻ là một link `download` tới /api/export. */
export function DataExportGrid() {
  return (
    <section>
      <div className="mb-5 flex items-center gap-3">
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-2 shadow-sm">
          <Download className="size-5 text-[var(--color-ink-muted)]" />
        </div>
        <h2 className="text-xl font-bold tracking-tight">Xuất dữ liệu (Backup)</h2>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {EXPORTS.map((item) => {
          const Icon = item.icon;
          return (
            <a
              key={item.href}
              href={item.href}
              download
              className="group relative flex flex-col justify-between overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-5 transition-all duration-300 hover:-translate-y-1 hover:border-[var(--color-border-hover)] hover:shadow-lg"
            >
              <div className={`absolute -right-8 -top-8 h-32 w-32 rounded-full bg-gradient-to-br ${item.color} opacity-40 blur-2xl transition-opacity duration-500 group-hover:opacity-100`}></div>
              <div className="relative z-10 mb-4">
                <div className={`mb-4 inline-flex rounded-xl bg-gradient-to-br ${item.color} border border-white/5 p-2.5 shadow-sm`}>
                  <Icon className="size-5" />
                </div>
                <h3 className="text-base font-bold text-[var(--color-ink)]">{item.title}</h3>
                <p className="mt-1.5 text-xs leading-relaxed text-[var(--color-ink-muted)]">{item.note}</p>
              </div>
              <div className="relative z-10 flex -translate-x-2.5 items-center text-xs font-semibold text-blue-500 opacity-0 transition-all duration-300 group-hover:translate-x-0 group-hover:opacity-100">
                Tải xuống ngay <ArrowRightToLine className="ml-1 size-3" />
              </div>
            </a>
          );
        })}
      </div>
    </section>
  );
}
