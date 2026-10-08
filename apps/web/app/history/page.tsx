import fs from "fs";
import path from "path";
import { IS_LOCAL, listBrowserHistory } from "@/lib/api";
import { ChromeHistoryDeleteForm } from "@/components/chrome-history-manager";
import { formatDateTime } from "@/lib/format";
import Link from "next/link";

export const dynamic = "force-dynamic";

interface ChromeHistoryEntry {
  url: string;
  title: string;
  visit_count: number;
  last_visit_time: string;
  profile?: string;
}

const PAGE_SIZE = 50;

export default async function HistoryPage({ searchParams }: { searchParams: Promise<{ q?: string; profile?: string; time?: string; from?: string; to?: string; sort?: string; page?: string }> }) {
  const sp = await searchParams;
  const currentQ = sp.q || "";
  const currentTime = sp.time || "all";
  const currentFrom = sp.from || "";
  const currentTo = sp.to || "";
  const currentSort = sp.sort === "asc" ? "asc" : "desc";
  const currentPage = Math.max(1, parseInt(sp.page || "1", 10) || 1);
  const dataPath = path.join(process.cwd(), "../../data/chrome-history.json");
  // Chế độ api: lọc theo q/profile và phân trang ngay ở core; time/from/to/sort không có ở core.
  const currentProfile = (sp.profile || "").trim();
  let data: { synced_at: string | null; source_path?: string; items: ChromeHistoryEntry[] } | null = null;
  let errorMsg = "";
  let apiTotal = 0;

  if (IS_LOCAL) {
    try {
      if (fs.existsSync(dataPath)) {
        const raw = fs.readFileSync(dataPath, "utf8");
        data = JSON.parse(raw);
      }
    } catch (err) {
      errorMsg = err instanceof Error ? err.message : String(err);
    }
  } else {
    try {
      const toEntry = (r: { url: string; title: string; visit_count: number; last_visit_at: string; profile: string }): ChromeHistoryEntry => ({
        url: r.url,
        title: r.title,
        visit_count: r.visit_count,
        last_visit_time: formatDateTime(r.last_visit_at),
        profile: r.profile,
      });
      let res = await listBrowserHistory({ q: currentQ, profile: currentProfile, limit: PAGE_SIZE, offset: (currentPage - 1) * PAGE_SIZE });
      // Trang vượt cuối (xoá dữ liệu, đổi filter): lấy lại trang cuối thay vì hiện bảng rỗng.
      if (res.items.length === 0 && res.total > 0) {
        const lastPage = Math.ceil(res.total / PAGE_SIZE);
        res = await listBrowserHistory({ q: currentQ, profile: currentProfile, limit: PAGE_SIZE, offset: (lastPage - 1) * PAGE_SIZE });
      }
      apiTotal = res.total;
      data = { synced_at: null, items: res.items.map(toEntry) };
    } catch (err) {
      errorMsg = err instanceof Error ? err.message : String(err);
    }
  }


  let filteredItems: ChromeHistoryEntry[] = [];
  if (data && IS_LOCAL) {
    filteredItems = data.items;
    
    // 1. Lọc theo từ khóa
    if (currentQ) {
      const q = currentQ.toLowerCase();
      filteredItems = filteredItems.filter(item => 
        (item.title && item.title.toLowerCase().includes(q)) || 
        (item.url && item.url.toLowerCase().includes(q))
      );
    }
    
    // 2. Lọc theo thời gian preset
    if (currentTime !== "all" && !currentFrom && !currentTo) {
      const now = new Date().getTime();
      const DAY_MS = 24 * 60 * 60 * 1000;
      let cutoff = 0;
      
      if (currentTime === "1d") cutoff = now - 1 * DAY_MS;
      else if (currentTime === "3d") cutoff = now - 3 * DAY_MS;
      else if (currentTime === "10d") cutoff = now - 10 * DAY_MS;
      else if (currentTime === "1m") cutoff = now - 30 * DAY_MS;
      else if (currentTime === "3m") cutoff = now - 90 * DAY_MS;
      else if (currentTime === "6m") cutoff = now - 180 * DAY_MS;
      
      if (cutoff > 0) {
        filteredItems = filteredItems.filter(item => {
          // item.last_visit_time is like "YYYY-MM-DD HH:MM:SS"
          const itemTime = new Date(item.last_visit_time.replace(" ", "T")).getTime();
          return itemTime >= cutoff;
        });
      }
    }

    // 3. Lọc theo khoảng ngày cụ thể (date picker)
    if (currentFrom || currentTo) {
      filteredItems = filteredItems.filter(item => {
        const itemDate = item.last_visit_time?.split(" ")[0] || ""; // "YYYY-MM-DD"
        if (currentFrom && itemDate < currentFrom) return false;
        if (currentTo && itemDate > currentTo) return false;
        return true;
      });
    }
  }

  // Sắp xếp theo thời gian
  if (IS_LOCAL && filteredItems.length > 0) {
    filteredItems.sort((a, b) => {
      const timeA = a.last_visit_time || "";
      const timeB = b.last_visit_time || "";
      return currentSort === "asc" ? timeA.localeCompare(timeB) : timeB.localeCompare(timeA);
    });
  }

  // Phân trang
  const totalItems = IS_LOCAL ? filteredItems.length : apiTotal;
  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));
  const safePage = Math.min(currentPage, totalPages);
  const startIdx = (safePage - 1) * PAGE_SIZE;
  const pagedItems = IS_LOCAL ? filteredItems.slice(startIdx, startIdx + PAGE_SIZE) : (data?.items ?? []);

  const makeLink = (updates: Record<string, string | undefined>) => {
    const q = new URLSearchParams();
    if (currentQ) q.set("q", currentQ);
    if (currentProfile) q.set("profile", currentProfile);
    if (currentTime !== "all") q.set("time", currentTime);
    if (currentFrom) q.set("from", currentFrom);
    if (currentTo) q.set("to", currentTo);
    if (currentSort !== "desc") q.set("sort", currentSort);
    // Giữ page khi chỉ thay đổi filter khác, nhưng cho phép override
    if (safePage > 1 && !('page' in updates)) q.set("page", String(safePage));
    
    for (const [k, v] of Object.entries(updates)) {
      if (v === undefined) q.delete(k);
      else q.set(k, v);
    }
    return `/history${q.toString() ? '?' + q.toString() : ''}`;
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Lịch sử duyệt web (Chrome)</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Danh sách các trang web bạn đã truy cập, được trích xuất từ dữ liệu cục bộ của Chrome{IS_LOCAL ? "" : " và lưu trong Postgres"}.
          {data?.source_path && (
            <span className="block mt-0.5 text-xs font-mono opacity-60">Nguồn: {data.source_path}</span>
          )}
        </p>
      </div>

      {errorMsg && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-600">
          Lỗi đọc dữ liệu: {errorMsg}
        </div>
      )}

      {!data && !errorMsg && (
        <div className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-ink-muted)]">
          Chưa có dữ liệu lịch sử nào. Vui lòng sang tab <b>Dữ liệu</b> để trích xuất lần đầu!
        </div>
      )}

      {data && (
        <div className="flex flex-col gap-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4">
          {/* Thanh tìm kiếm */}
          <form method="get" className="flex gap-2">
            {currentTime !== "all" && <input type="hidden" name="time" value={currentTime} />}
            {currentFrom && <input type="hidden" name="from" value={currentFrom} />}
            {currentTo && <input type="hidden" name="to" value={currentTo} />}
            {currentProfile && <input type="hidden" name="profile" value={currentProfile} />}
            <input
              type="search"
              name="q"
              defaultValue={currentQ}
              placeholder="Tìm kiếm theo tiêu đề hoặc link..."
              className="flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm"
            />
            <button type="submit" className="rounded-md bg-[var(--color-accent)] px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-[var(--color-accent-hover)]">
              Tìm
            </button>
          </form>

          {!IS_LOCAL && (
            <form method="get" className="flex flex-wrap items-center gap-2">
              {currentQ && <input type="hidden" name="q" value={currentQ} />}
              <span className="text-sm font-medium w-24">Profile:</span>
              <input
                type="text"
                name="profile"
                defaultValue={currentProfile}
                placeholder="Tất cả profile (vd: Default)"
                maxLength={200}
                className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-sm"
              />
              <button type="submit" className="rounded-md bg-[var(--color-accent)] px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-[var(--color-accent-hover)]">
                Lọc
              </button>
            </form>
          )}

          {/* Filter thời gian preset (chỉ chế độ file; core chưa hỗ trợ) */}
          {IS_LOCAL && (<>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium w-24">Thời gian:</span>
            {[
              { id: "all", label: "Tất cả" },
              { id: "1d", label: "1 Ngày" },
              { id: "3d", label: "3 Ngày" },
              { id: "10d", label: "10 Ngày" },
              { id: "1m", label: "1 Tháng" },
              { id: "3m", label: "3 Tháng" },
              { id: "6m", label: "6 Tháng" }
            ].map(so => (
              <Link
                key={so.id}
                href={makeLink({ time: so.id === "all" ? undefined : so.id, from: undefined, to: undefined })}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  currentTime === so.id && !currentFrom && !currentTo
                    ? "bg-[var(--color-accent)] text-white"
                    : "border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)]"
                }`}
              >
                {so.label}
              </Link>
            ))}
          </div>

          {/* Filter theo khoảng ngày cụ thể */}
          <form method="get" className="flex flex-wrap items-center gap-2">
            {currentQ && <input type="hidden" name="q" value={currentQ} />}
            <span className="text-sm font-medium w-24">Theo ngày:</span>
            <input
              type="date"
              name="from"
              defaultValue={currentFrom}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-sm"
            />
            <span className="text-xs text-[var(--color-ink-muted)]">→</span>
            <input
              type="date"
              name="to"
              defaultValue={currentTo}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-sm"
            />
            <button
              type="submit"
              className="rounded-md bg-[var(--color-accent)] px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-[var(--color-accent-hover)]"
            >
              Lọc
            </button>
            {(currentFrom || currentTo) && (
              <Link
                href={makeLink({ from: undefined, to: undefined, time: undefined })}
                className="rounded-md border border-[var(--color-border)] px-3 py-1 text-xs font-medium hover:bg-[var(--color-surface-hover)] transition-colors"
              >
                Xoá bộ lọc ngày
              </Link>
            )}
          </form>
          </>)}
        </div>
      )}

      {!IS_LOCAL && !errorMsg && <ChromeHistoryDeleteForm defaultProfile={currentProfile} />}

      {data && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Tổng: {totalItems} kết quả</span>
            {data.synced_at && (
              <span className="text-xs text-[var(--color-ink-muted)]">
                Đồng bộ lần cuối: {formatDateTime(data.synced_at)}
              </span>
            )}
          </div>

          {pagedItems.length === 0 ? (
            <div className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-ink-muted)]">
              {currentQ || currentProfile || (IS_LOCAL && (currentTime !== "all" || currentFrom || currentTo))
                ? "Không có bản ghi nào khớp bộ lọc hiện tại."
                : IS_LOCAL
                  ? <>Chưa có dữ liệu lịch sử nào. Vui lòng sang tab <b>Dữ liệu</b> để trích xuất lần đầu!</>
                  : <>Chưa có lịch sử duyệt web nào trong Postgres. Sang tab <b>Dữ liệu</b> để cào từ Chrome hoặc nhập file chrome-history.json.</>}
            </div>
          ) : (
          <div className="overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-[var(--color-border)] bg-[var(--color-surface-raised)]">
                <tr>
                  <th className="px-4 py-2 font-medium text-[var(--color-ink-muted)]">
                    {!IS_LOCAL ? "Thời gian" : <Link
                      href={makeLink({ sort: currentSort === "desc" ? "asc" : undefined, page: "1" })}
                      className="inline-flex items-center gap-1 hover:text-[var(--color-accent)] transition-colors"
                      title={currentSort === "desc" ? "Đang: Mới nhất trước — Bấm để đổi" : "Đang: Cũ nhất trước — Bấm để đổi"}
                    >
                      Thời gian
                      <span className="text-xs">{currentSort === "desc" ? "↓" : "↑"}</span>
                    </Link>}
                  </th>
                  <th className="px-4 py-2 font-medium text-[var(--color-ink-muted)]">Tiêu đề & URL</th>
                  <th className="px-4 py-2 font-medium text-[var(--color-ink-muted)] text-right">Lượt truy cập</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {pagedItems.map((item, idx) => (
                  <tr key={`${startIdx + idx}`} className="hover:bg-[var(--color-surface-hover)] transition-colors">
                    <td className="px-4 py-3 align-top whitespace-nowrap text-xs text-[var(--color-ink-muted)]">
                      {item.last_visit_time}
                      {item.profile && <span className="block opacity-60">{item.profile}</span>}
                    </td>
                    <td className="px-4 py-3 align-top">
                      <div className="flex flex-col gap-1 max-w-xl">
                        <span className="font-medium truncate" title={item.title}>
                          {item.title || "Không có tiêu đề"}
                        </span>
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-[var(--color-accent)] truncate hover:underline"
                          title={item.url}
                        >
                          {item.url}
                        </a>
                      </div>
                    </td>
                    <td className="px-4 py-3 align-top text-right text-xs font-mono">
                      {item.visit_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          )}

          {/* Thanh phân trang */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-4 py-3">
              <span className="text-xs text-[var(--color-ink-muted)]">
                Tổng: {totalItems} kết quả
              </span>
              <div className="flex items-center gap-2">
                {safePage > 1 ? (
                  <Link
                    href={makeLink({ page: String(safePage - 1) })}
                    className="rounded-md border border-[var(--color-border)] px-3 py-1 text-xs font-medium hover:bg-[var(--color-surface-hover)] transition-colors"
                  >
                    ← Trước
                  </Link>
                ) : (
                  <span className="rounded-md border border-[var(--color-border)] px-3 py-1 text-xs font-medium opacity-40 cursor-not-allowed">← Trước</span>
                )}
                <span className="text-sm font-medium">
                  Trang {safePage} / {totalPages}
                </span>
                {safePage < totalPages ? (
                  <Link
                    href={makeLink({ page: String(safePage + 1) })}
                    className="rounded-md border border-[var(--color-border)] px-3 py-1 text-xs font-medium hover:bg-[var(--color-surface-hover)] transition-colors"
                  >
                    Sau →
                  </Link>
                ) : (
                  <span className="rounded-md border border-[var(--color-border)] px-3 py-1 text-xs font-medium opacity-40 cursor-not-allowed">Sau →</span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
