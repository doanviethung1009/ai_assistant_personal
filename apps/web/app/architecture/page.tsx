import Link from "next/link";

import {
  BackendLayersDiagram,
  DataSourceDiagram,
  DeploymentDiagram,
  TaskLifecycleDiagram,
  WriteFlowDiagram,
} from "@/components/architecture-diagrams";
import { DiagramDefs } from "@/components/diagram";
import { MotionToggle } from "@/components/motion-toggle";
import { DATA_SOURCE } from "@/lib/api";

export const metadata = {
  title: "Kiến trúc · Builder AI Assistant",
};

const SECTIONS = [
  { id: "deployment", label: "Triển khai" },
  { id: "write-flow", label: "Luồng ghi" },
  { id: "lifecycle", label: "Vòng đời task" },
  { id: "data-source", label: "Nguồn dữ liệu" },
  { id: "layers", label: "Phân lớp backend" },
];

export default function ArchitecturePage() {
  return (
    <div className="flex flex-col gap-6">
      {/* Marker mũi tên và filter đổ bóng, khai báo một lần cho cả trang */}
      <DiagramDefs />

      <div>
        <h1 className="text-xl font-semibold tracking-tight">Kiến trúc</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Năm sơ đồ mô tả app hoạt động thế nào: container nói với nhau ra sao,
          một lần ghi dữ liệu đi qua những đâu, task chuyển trạng thái theo luật
          nào.
        </p>
      </div>

      {/* ── Mục lục ─────────────────────────────────────────────────── */}
      <nav aria-label="Mục lục sơ đồ">
        <ul className="flex flex-wrap gap-2">
          {SECTIONS.map((section) => (
            <li key={section.id}>
              <a
                href={`#${section.id}`}
                className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-1.5 text-xs transition-colors hover:bg-[var(--color-surface-hover)]"
              >
                {section.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      {/* ── Chú giải màu ────────────────────────────────────────────── */}
      <section className="rounded-lg border border-dashed border-[var(--color-border)] p-3">
        <h2 className="text-xs font-semibold text-[var(--color-ink-muted)]">
          Cách đọc màu
        </h2>
        <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1.5 text-xs">
          <div className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-3 rounded border"
              style={{
                borderColor: "var(--color-accent)",
                background:
                  "color-mix(in srgb, var(--color-accent) 14%, var(--color-surface))",
              }}
            />
            <dt className="text-[var(--color-ink-muted)]">Ứng dụng của mình</dt>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-3 rounded border"
              style={{
                borderColor: "var(--color-success)",
                background:
                  "color-mix(in srgb, var(--color-success) 14%, var(--color-surface))",
              }}
            />
            <dt className="text-[var(--color-ink-muted)]">Nơi lưu dữ liệu</dt>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-3 rounded border"
              style={{
                borderColor: "var(--color-warn)",
                background:
                  "color-mix(in srgb, var(--color-warn) 14%, var(--color-surface))",
              }}
            />
            <dt className="text-[var(--color-ink-muted)]">Logic nghiệp vụ, LLM</dt>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-3 rounded border"
              style={{
                borderColor: "var(--color-danger)",
                background:
                  "color-mix(in srgb, var(--color-danger) 14%, var(--color-surface))",
              }}
            />
            <dt className="text-[var(--color-ink-muted)]">Chặn hoặc xoá</dt>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-3 rounded border border-dashed"
              style={{ borderColor: "var(--color-border)" }}
            />
            <dt className="text-[var(--color-ink-muted)]">
              Nhóm hoặc trạng thái tạm
            </dt>
          </div>
        </dl>
      </section>

      {/* ── Sơ đồ ───────────────────────────────────────────────────── */}
      <MotionToggle>
        <section id="deployment" className="scroll-mt-6">
          <DeploymentDiagram />
        </section>

        <section id="write-flow" className="scroll-mt-6">
          <WriteFlowDiagram />
        </section>

        <section id="lifecycle" className="scroll-mt-6">
          <TaskLifecycleDiagram />
        </section>

        <section id="data-source" className="scroll-mt-6">
          <DataSourceDiagram />
          <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
            Hệ thống lúc này đang chạy ở chế độ{" "}
            <code className="rounded bg-black/30 px-1">
              DATA_SOURCE={DATA_SOURCE}
            </code>
            .
          </p>
        </section>

        <section id="layers" className="scroll-mt-6">
          <BackendLayersDiagram />
        </section>
      </MotionToggle>

      {/* ── Điều gì chưa có trong sơ đồ ─────────────────────────────── */}
      <section className="rounded-lg border border-dashed border-[var(--color-border)] p-4">
        <h2 className="text-sm font-semibold">Chưa có trong sơ đồ</h2>
        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Các phần từ Phase 2 trở đi chưa được vẽ vì chưa tồn tại trong code:
          MCP server cho Jira và Calendar, scheduler poll, Telegram bot, và luồng
          deploy có approval gate. Khi nào code có thật thì sơ đồ mới thêm, để
          trang này không mô tả thứ không tồn tại.
        </p>
        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Tiến độ từng phần xem ở{" "}
          <Link href="/roadmap" className="text-[var(--color-accent)] underline">
            Lộ trình
          </Link>
          . Lý do đằng sau từng quyết định kiến trúc xem ở{" "}
          <Link href="/docs" className="text-[var(--color-accent)] underline">
            Tài liệu
          </Link>
          .
        </p>
      </section>
    </div>
  );
}
