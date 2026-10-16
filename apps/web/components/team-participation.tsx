import { PERIOD_RANGES, type ResolvedPeriod } from "@/lib/period";
import type { Participation } from "@/lib/types";

/** Số người hiện tối đa trong mỗi project; phần còn lại gộp vào một dòng "và N người khác". */
const MAX_MEMBERS_SHOWN = 10;

/**
 * Dashboard tham dự dự án của nhóm: mỗi project, mỗi người gánh bao nhiêu % task.
 *
 * % = task của người đó / TỔNG task của project (kể cả người không được chọn và task chưa
 * giao), nên chọn thêm hay bớt người không làm các số khác đổi. Chỉ task công việc chưa huỷ.
 *
 * Ô chọn người là form GET thuần (không cần client JS), lựa chọn nằm trên URL nên chia sẻ được.
 * Nằm ở route riêng (/team/participation) để lọc danh sách ở /team không phải tính lại mục này.
 */
export function TeamParticipation({
  data,
  selectedParam,
  period,
  action = "/team/participation",
}: {
  data: Participation;
  /** Người đã chọn qua URL; rỗng nghĩa là chưa chọn ai (đang xem tất cả). */
  selectedParam: string[];
  /** Khoảng thời gian đang áp, để điền lại vào form. */
  period: ResolvedPeriod;
  /** Trang nhận form; cũng là đích của nút "Xem tất cả". */
  action?: string;
}) {
  const picked = new Set(selectedParam);

  return (
    <section
      aria-label="Tỉ lệ tham dự dự án"
      className="flex flex-col gap-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-6 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold tracking-tight">Tỉ lệ tham dự dự án</h2>
          <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
            Phần việc của mỗi người trong từng project (task công việc chưa huỷ, gồm cả đã xong).
            % tính trên tổng task của project{period.range !== "all" ? " trong khoảng thời gian đã chọn" : ""}.
            Thanh chia hai đoạn:{" "}
            <span className="font-medium text-emerald-600 dark:text-emerald-400">xanh lá là đã xong</span>,
            phần còn lại là đang mở.
          </p>
        </div>
      </div>

      <form method="get" action={action} className="flex flex-col gap-3">
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm font-medium">
            Chọn người phân tích{" "}
            <span className="font-normal text-[var(--color-ink-muted)]">
              ({picked.size === 0 ? "đang xem tất cả" : `${picked.size} người`})
            </span>
          </legend>
          {data.assignees.length === 0 ? (
            <p className="text-sm text-[var(--color-ink-muted)]">Chưa có task công việc nào được giao.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {data.assignees.map((a) => (
                <label
                  key={a.name}
                  className="flex cursor-pointer items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-xs has-[:checked]:border-blue-500 has-[:checked]:bg-blue-500/10"
                >
                  <input
                    type="checkbox"
                    name="people"
                    value={a.name}
                    defaultChecked={picked.has(a.name)}
                    className="accent-blue-500"
                  />
                  <span className="font-medium">{a.name}</span>
                  <span className="tabular-nums opacity-60">{a.total}</span>
                </label>
              ))}
            </div>
          )}
        </fieldset>
        <fieldset className="flex flex-wrap items-end gap-3">
          <legend className="mb-1 text-sm font-medium">
            Thời gian{" "}
            <span className="font-normal text-[var(--color-ink-muted)]">
              (theo ngày hoạt động: ngày hoàn thành với task đã xong, ngày cập nhật với task còn lại)
            </span>
          </legend>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-[var(--color-ink-muted)]">Khoảng</span>
            <select
              name="range"
              defaultValue={period.range}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm"
            >
              {PERIOD_RANGES.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-[var(--color-ink-muted)]">Từ ngày</span>
            <input
              type="date"
              name="from"
              defaultValue={period.range === "custom" ? period.from : undefined}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-[var(--color-ink-muted)]">Đến ngày</span>
            <input
              type="date"
              name="to"
              defaultValue={period.range === "custom" ? period.to : undefined}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm"
            />
          </label>
          <p className="basis-full text-xs text-[var(--color-ink-muted)]">
            Hai ô ngày chỉ dùng khi chọn &ldquo;Tuỳ chọn khoảng ngày&rdquo;; bỏ trống một ô nghĩa là
            không giới hạn phía đó.
          </p>
        </fieldset>
        <div className="flex gap-2">
          <button
            type="submit"
            className="rounded-md bg-[var(--color-accent)] px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-[var(--color-accent-hover)]"
          >
            Phân tích
          </button>
          {(picked.size > 0 || period.range !== "all") && (
            <a
              href={action}
              className="rounded-md border border-[var(--color-border)] px-4 py-1.5 text-sm font-medium hover:bg-[var(--color-surface-hover)]"
            >
              Đặt lại
            </a>
          )}
        </div>
      </form>

      {data.projects.length === 0 ? (
        <p className="text-sm text-[var(--color-ink-muted)]">
          {picked.size > 0
            ? "Những người đã chọn chưa tham gia project nào trong khoảng thời gian này."
            : period.range !== "all"
              ? "Không có task nào có hoạt động trong khoảng thời gian này."
              : "Chưa có dữ liệu để phân tích."}
        </p>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {data.projects.map((project) => {
            const shown = project.members.slice(0, MAX_MEMBERS_SHOWN);
            const hidden = project.members.length - shown.length;
            return (
              <li
                key={project.project_id ?? "none"}
                className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
              >
                <div className="mb-3 flex items-baseline justify-between gap-3">
                  <h3 className="truncate text-sm font-semibold" title={project.name}>
                    {project.key ? <span className="mr-1.5 text-xs opacity-60">{project.key}</span> : null}
                    {project.name}
                  </h3>
                  <span className="shrink-0 text-xs tabular-nums text-[var(--color-ink-muted)]">
                    {project.total} task
                  </span>
                </div>
                <ul className="flex flex-col gap-2.5">
                  {shown.map((m) => (
                    <li key={m.assignee}>
                      <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
                        <span className="truncate" title={m.assignee}>
                          {m.assignee}
                        </span>
                        <span className="shrink-0 tabular-nums text-[var(--color-ink-muted)]">
                          <span className="text-emerald-600 dark:text-emerald-400">{m.done} xong</span>
                          {" · "}
                          {m.open} đang mở {" · "}
                          <strong className="text-[var(--color-ink)]">{m.percent}%</strong>
                        </span>
                      </div>
                      <div
                        role="progressbar"
                        aria-label={`${m.assignee} trong ${project.name}`}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={m.percent}
                        className="h-2 overflow-hidden rounded-full bg-[var(--color-border)]"
                      >
                        {/* Cả thanh dài theo % của project; bên trong chia hai đoạn theo xong / đang mở. */}
                        <div className="flex h-full overflow-hidden rounded-full" style={{ width: `${m.percent}%` }}>
                          <div className="h-full bg-emerald-500" style={{ flexGrow: m.done }} title={`${m.done} xong`} />
                          <div
                            className="h-full bg-blue-500"
                            style={{ flexGrow: m.open, backgroundColor: project.color ?? undefined }}
                            title={`${m.open} đang mở`}
                          />
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
                {hidden > 0 && (
                  <p className="mt-2 text-xs text-[var(--color-ink-muted)]">và {hidden} người khác</p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
