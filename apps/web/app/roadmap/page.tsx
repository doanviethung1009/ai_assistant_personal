import Link from "next/link";

import {
  ItemList,
  PhaseFlow,
  ProgressBar,
  StatusLegend,
  StatusPill,
} from "@/components/roadmap-parts";
import { DATA_SOURCE, getStats, listProjects } from "@/lib/api";
import { FOUNDATION, PHASES, progressPercent } from "@/lib/roadmap";
import type { Stats } from "@/lib/types";

export const dynamic = "force-dynamic";

const SOURCE_LABELS: Record<string, string> = {
  api: "Postgres qua core API",
  file: "File JSON cục bộ",
  memory: "Bộ nhớ tạm",
};

/** Số liệu sống của hệ thống, để lộ trình không chỉ là văn bản tĩnh. */
async function loadSnapshot(): Promise<{
  stats: Stats | null;
  projectCount: number | null;
  error: string | null;
}> {
  try {
    const [stats, projects] = await Promise.all([getStats(), listProjects(true)]);
    return { stats, projectCount: projects.length, error: null };
  } catch (error) {
    return {
      stats: null,
      projectCount: null,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-2">
      <dt className="text-xs text-[var(--color-ink-muted)]">{label}</dt>
      <dd className="mt-0.5 text-sm font-semibold">{value}</dd>
    </div>
  );
}

export default async function RoadmapPage() {
  const snapshot = await loadSnapshot();

  const allItems = [...PHASES.flatMap((phase) => phase.items), ...FOUNDATION];
  const overall = progressPercent(allItems);

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Lộ trình dự án</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Trạng thái thật của những gì đã build, đang build và chưa build. Mục
          &ldquo;Chưa verify&rdquo; nghĩa là code đã viết nhưng chưa từng chạy.
        </p>
      </div>

      {/* ── Tiến độ tổng ────────────────────────────────────────────── */}
      <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold">Tiến độ tổng thể</h2>
          <span className="text-sm tabular-nums text-[var(--color-ink-muted)]">
            {overall}% · {allItems.length} mục
          </span>
        </div>
        <div className="mt-3">
          <ProgressBar percent={overall} />
        </div>
        <div className="mt-3">
          <StatusLegend items={allItems} />
        </div>
        <p className="mt-3 text-xs text-[var(--color-ink-muted)]">
          Mục &ldquo;Chưa verify&rdquo; và &ldquo;Đang làm&rdquo; tính nửa điểm,
          nên con số này bảo thủ hơn cảm giác.
        </p>
      </section>

      {/* ── Số liệu sống ────────────────────────────────────────────── */}
      <section>
        <h2 className="mb-3 text-sm font-semibold">Hệ thống lúc này</h2>
        {snapshot.error ? (
          <p className="rounded-lg border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10 p-3 text-xs text-[var(--color-warn)]">
            Không đọc được số liệu: {snapshot.error}
          </p>
        ) : (
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard
              label="Nguồn dữ liệu"
              value={SOURCE_LABELS[DATA_SOURCE] ?? DATA_SOURCE}
            />
            <StatCard label="Task đang mở" value={snapshot.stats?.open_total ?? 0} />
            <StatCard label="Trong thùng rác" value={snapshot.stats?.trash_total ?? 0} />
            <StatCard label="Dự án" value={snapshot.projectCount ?? 0} />
          </dl>
        )}
      </section>

      {/* ── Flow 5 phase ────────────────────────────────────────────── */}
      <section>
        <h2 className="mb-3 text-sm font-semibold">Năm phase</h2>
        <PhaseFlow phases={PHASES} />
      </section>

      {/* ── Chi tiết từng phase ─────────────────────────────────────── */}
      <section className="flex flex-col gap-4">
        {PHASES.map((phase) => {
          const percent = progressPercent(phase.items);

          return (
            <article
              key={phase.key}
              id={`phase-${phase.id}`}
              className="scroll-mt-6 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4"
            >
              <header className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="flex items-center gap-2 text-sm font-semibold">
                    <span className="text-[var(--color-ink-muted)]">
                      Phase {phase.id}
                    </span>
                    {phase.title}
                  </h3>
                  <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
                    {phase.goal}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-xs tabular-nums text-[var(--color-ink-muted)]">
                    {percent}%
                  </span>
                  <StatusPill status={phase.status} />
                </div>
              </header>

              <div className="mt-3">
                <ProgressBar percent={percent} />
              </div>

              <p className="mt-3 rounded-md border border-[var(--color-border)] bg-black/20 px-3 py-2 text-xs text-[var(--color-ink-muted)]">
                <span className="font-medium text-[var(--color-ink)]">
                  Kiến trúc kèm theo:
                </span>{" "}
                {phase.architecture}
              </p>

              <div className="mt-3">
                <ItemList items={phase.items} />
              </div>
            </article>
          );
        })}
      </section>

      {/* ── Nền tảng ────────────────────────────────────────────────── */}
      <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4">
        <h2 className="text-sm font-semibold">Nền tảng dùng chung</h2>
        <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
          Không thuộc phase nào nhưng mọi phase đều dựa vào.
        </p>
        <div className="mt-3">
          <ItemList items={FOUNDATION} />
        </div>
      </section>

      {/* ── Việc kế tiếp ────────────────────────────────────────────── */}
      <section className="rounded-lg border border-dashed border-[var(--color-border)] p-4">
        <h2 className="text-sm font-semibold">Ba việc kế tiếp, theo thứ tự</h2>
        <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-sm text-[var(--color-ink-muted)]">
          <li>
            Chạy <code>make bootstrap</code> trên Ubuntu để dựng Postgres và core
            API, sinh initial migration, rồi sửa tới khi{" "}
            <code>make smoke</code> pass sạch.
          </li>
          <li>
            <code>make mon-up</code>, xác nhận Prometheus scrape được{" "}
            <code>api:8000/metrics</code> và blackbox probe được{" "}
            <code>/health/ready</code>.
          </li>
          <li>
            Chốt <strong>Jira Cloud hay Data Center</strong>. Câu này đang chặn
            toàn bộ Phase 2 vì auth và endpoint khác nhau hoàn toàn.
          </li>
        </ol>
        <p className="mt-3 text-xs text-[var(--color-ink-muted)]">
          Chi tiết kiến trúc và lý do đằng sau từng quyết định nằm ở tab{" "}
          <Link href="/docs" className="text-[var(--color-accent)] underline">
            Tài liệu
          </Link>
          .
        </p>
      </section>
    </div>
  );
}
