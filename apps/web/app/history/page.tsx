import fs from "fs";
import path from "path";
import { formatDateTime } from "@/lib/format";
import Link from "next/link";

export const dynamic = "force-dynamic";

interface ChromeHistoryEntry {
  url: string;
  title: string;
  visit_count: number;
  last_visit_time: string;
}

export default async function HistoryPage({ searchParams }: { searchParams: Promise<{ q?: string; time?: string }> }) {
  const sp = await searchParams;
  const currentQ = sp.q || "";
  const currentTime = sp.time || "all";
  const dataPath = path.join(process.cwd(), "../../data/chrome-history.json");
  let data: { synced_at: string; items: ChromeHistoryEntry[] } | null = null;
  let errorMsg = "";

  try {
    if (fs.existsSync(dataPath)) {
      const raw = fs.readFileSync(dataPath, "utf8");
      data = JSON.parse(raw);
    }
  } catch (err: any) {
    errorMsg = err.message;
  }


  let filteredItems: ChromeHistoryEntry[] = [];
  if (data) {
    filteredItems = data.items;
    
    // 1. Lọc theo từ khóa
    if (currentQ) {
      const q = currentQ.toLowerCase();
      filteredItems = filteredItems.filter(item => 
        (item.title && item.title.toLowerCase().includes(q)) || 
        (item.url && item.url.toLowerCase().includes(q))
      );
    }
    
    // 2. Lọc theo thời gian
    if (currentTime !== "all") {
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
  }

  const makeLink = (updates: Record<string, string | undefined>) => {
    const q = new URLSearchParams();
    if (currentQ) q.set("q", currentQ);
    if (currentTime !== "all") q.set("time", currentTime);
    
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
          Danh sách các trang web bạn đã truy cập, được trích xuất từ dữ liệu cục bộ của Chrome.
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
          <form method="get" className="flex gap-2">
            {currentTime !== "all" && <input type="hidden" name="time" value={currentTime} />}
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
                href={makeLink({ time: so.id === "all" ? undefined : so.id })}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  currentTime === so.id
                    ? "bg-[var(--color-accent)] text-white"
                    : "border border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)]"
                }`}
              >
                {so.label}
              </Link>
            ))}
          </div>
        </div>
      )}

      {data && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Tổng cộng: {filteredItems.length} bản ghi</span>
            <span className="text-xs text-[var(--color-ink-muted)]">
              Đồng bộ lần cuối: {formatDateTime(data.synced_at)}
            </span>
          </div>

          <div className="overflow-x-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-[var(--color-border)] bg-[var(--color-surface-raised)]">
                <tr>
                  <th className="px-4 py-2 font-medium text-[var(--color-ink-muted)]">Thời gian</th>
                  <th className="px-4 py-2 font-medium text-[var(--color-ink-muted)]">Tiêu đề & URL</th>
                  <th className="px-4 py-2 font-medium text-[var(--color-ink-muted)] text-right">Lượt truy cập</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {filteredItems.slice(0, 1000).map((item, idx) => (
                  <tr key={idx} className="hover:bg-[var(--color-surface-hover)] transition-colors">
                    <td className="px-4 py-3 align-top whitespace-nowrap text-xs text-[var(--color-ink-muted)]">
                      {item.last_visit_time}
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
            {filteredItems.length > 1000 && (
              <div className="p-4 text-center text-xs text-[var(--color-ink-muted)] border-t border-[var(--color-border)]">
                Hiển thị 1000 bản ghi gần nhất. Xem toàn bộ trong file data/chrome-history.json.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
