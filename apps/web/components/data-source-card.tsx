import type { LucideIcon } from "lucide-react";
import {
  ArrowRightToLine,
  HardDrive,
  MemoryStick,
  Server,
  Terminal,
} from "lucide-react";

import { DATA_SOURCE } from "@/lib/api";
import { dataFilePath } from "@/lib/store/json-file";

/**
 * Thẻ nguồn dữ liệu đang dùng + hướng dẫn đổi nguồn.
 *
 * Không có nút đổi nguồn trên web vì DATA_SOURCE là hằng số đọc một lần khi
 * server khởi động; đổi phải khởi động lại (make use-db / make use-local).
 */

const SOURCE_INFO: Record<
  string,
  { label: string; detail: string; tone: "ok" | "warn"; icon: LucideIcon }
> = {
  api: {
    label: "Core API & Postgres",
    detail: "Dữ liệu nằm trong Postgres, do apps/core quản lý. Đây là chế độ thật.",
    tone: "ok",
    icon: Server,
  },
  file: {
    label: "File JSON cục bộ",
    detail: "Ghi nguyên tử qua file tạm rồi rename, giữ thêm một bản .bak.",
    tone: "ok",
    icon: HardDrive,
  },
  memory: {
    label: "Bộ nhớ tạm (RAM)",
    detail: "Dữ liệu mất khi dev server khởi động lại. Chuyển sang file nếu muốn giữ.",
    tone: "warn",
    icon: MemoryStick,
  },
};


interface Props {
  taskCount: number;
  projectCount: number;
  noteCount: number;
}

export function DataSourceCard({ taskCount, projectCount, noteCount }: Props) {
  const info = SOURCE_INFO[DATA_SOURCE] ?? SOURCE_INFO.api!;
  const SourceIcon = info.icon;

  return (
    <>
  <section className={`group relative overflow-hidden rounded-xl border p-6 transition-all duration-300 hover:shadow-lg ${info.tone === "warn"
      ? "border-amber-500/30 bg-amber-500/5 dark:bg-amber-900/10"
      : "border-[var(--color-border)] bg-gradient-to-br from-[var(--color-surface-raised)] to-[var(--color-surface)]"
    }`}>
    <div className="absolute right-0 top-0 -mt-4 -mr-4 h-32 w-32 rounded-full bg-gradient-to-br from-blue-500/10 to-purple-500/10 blur-2xl transition-all duration-700 group-hover:scale-[2]"></div>
    
    <div className="relative flex flex-col md:flex-row md:items-center justify-between gap-6">
      <div>
        <div className="flex items-center gap-3">
          <div className={`p-2.5 rounded-xl shadow-sm ${info.tone === "warn" ? "bg-amber-500/20 text-amber-600" : "bg-blue-500/10 text-blue-600 border border-blue-500/20"}`}>
            <SourceIcon className="size-5" />
          </div>
          <h2 className="text-lg font-bold tracking-tight">Nguồn dữ liệu: {info.label}</h2>
          <code className="rounded-full bg-[var(--color-surface-hover)] border border-[var(--color-border)] px-2.5 py-0.5 text-[11px] font-mono tracking-wider shadow-sm">
            DATA_SOURCE={DATA_SOURCE}
          </code>
        </div>
        <p className="mt-2.5 text-sm text-[var(--color-ink-muted)]">{info.detail}</p>
        {DATA_SOURCE === "file" && (
          <p className="mt-3 text-xs text-[var(--color-ink-muted)] flex items-center gap-1.5">
            <HardDrive className="size-3.5" />
            Đường dẫn: <code className="bg-[var(--color-surface-hover)] px-2 py-1 rounded-md border border-[var(--color-border)] font-mono shadow-inner">{dataFilePath()}</code>
          </p>
        )}
      </div>

      {/* Stats Badges */}
      <div className="flex gap-3">
        {[
          { label: "Task", value: taskCount, color: "text-blue-600 bg-blue-500/10 border-blue-500/20" },
          { label: "Project", value: projectCount, color: "text-purple-600 bg-purple-500/10 border-purple-500/20" },
          { label: "Sổ tay", value: noteCount, color: "text-emerald-600 bg-emerald-500/10 border-emerald-500/20" }
        ].map(stat => (
          <div key={stat.label} className={`flex flex-col items-center justify-center px-5 py-3 rounded-xl border ${stat.color} transition-transform duration-300 hover:-translate-y-1 hover:shadow-md`}>
            <span className="text-2xl font-black tabular-nums leading-none tracking-tight">{stat.value}</span>
            <span className="text-[10px] uppercase tracking-widest font-bold opacity-70 mt-1.5">{stat.label}</span>
          </div>
        ))}
      </div>
    </div>
  </section>

  {/* Accordion for Changing Data Source */}
  <details className="group rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] [&_summary::-webkit-details-marker]:hidden shadow-sm transition-all hover:shadow-md">
    <summary className="flex cursor-pointer items-center justify-between p-5 font-medium transition-colors hover:bg-[var(--color-surface-hover)] rounded-xl">
      <div className="flex items-center gap-3">
        <div className="p-1.5 bg-[var(--color-surface-raised)] border border-[var(--color-border)] rounded-md shadow-sm">
          <ArrowRightToLine className="size-4 text-[var(--color-ink-muted)]" />
        </div>
        <span className="font-semibold text-[var(--color-ink)]">Hướng dẫn đổi nguồn dữ liệu</span>
      </div>
      <span className="transition-transform duration-300 group-open:rotate-180 text-[var(--color-ink-muted)]">▼</span>
    </summary>
    <div className="border-t border-[var(--color-border)] p-6 bg-[var(--color-surface-raised)] rounded-b-xl text-sm text-[var(--color-ink-muted)]">
      <p className="mb-5 leading-relaxed">
        Không có nút bấm trên web — đổi <code>DATA_SOURCE</code> cần
        Next.js khởi động lại để đọc biến môi trường mới. Chọn đúng mục dưới đây tùy theo môi trường bạn đang chạy:
      </p>
      <div className="grid gap-5 md:grid-cols-2">
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-sm">
          <p className="font-semibold text-[var(--color-ink)] flex items-center gap-2 mb-4 text-base">
            <Server className="size-4 text-blue-500" /> Docker (make up)
          </p>
          <ul className="space-y-3 text-xs">
            <li className="flex justify-between items-center bg-[var(--color-surface-raised)] p-2.5 rounded-lg border border-[var(--color-border)] shadow-sm">
              <span className="font-medium">Sang Postgres:</span> <code className="font-mono text-blue-500 bg-blue-500/10 px-2 py-0.5 rounded">make use-db</code>
            </li>
            <li className="flex justify-between items-center bg-[var(--color-surface-raised)] p-2.5 rounded-lg border border-[var(--color-border)] shadow-sm">
              <span className="font-medium">Sang file JSON:</span> <code className="font-mono text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded">make use-local</code>
            </li>
          </ul>
          <p className="mt-4 text-xs opacity-70 italic">Các lệnh này tự sửa <code>.env</code> và chạy lại container tự động.</p>
        </div>
        
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-sm">
          <p className="font-semibold text-[var(--color-ink)] flex items-center gap-2 mb-4 text-base">
            <Terminal className="size-4 text-purple-500" /> Local (npm run dev)
          </p>
          <p className="text-xs mb-3 leading-relaxed">Sửa biến trong file <code>apps/web/.env.local</code> rồi restart terminal:</p>
          <pre className="overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[#0d1117] p-3 text-[13px] font-mono text-gray-300 shadow-inner">
            <code><span className="text-gray-500"># apps/web/.env.local</span><br/>DATA_SOURCE=<span className="text-green-400">file</span> <span className="text-gray-500"># memory, api</span></code>
          </pre>
        </div>
      </div>
    </div>
  </details>

    </>
  );
}
