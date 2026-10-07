import sys
file_path = "apps/web/app/history/page.tsx"
with open(file_path, "r") as f:
    c = f.read()

# Replace imports and add Link
c = c.replace(
    'import { formatFullPlainDate } from "@/lib/format";',
    'import { formatFullPlainDate } from "@/lib/format";\nimport Link from "next/link";'
)

# Replace signature
c = c.replace(
    'export default async function HistoryPage() {',
    'export default async function HistoryPage({ searchParams }: { searchParams: Promise<{ q?: string; time?: string }> }) {\n  const sp = await searchParams;\n  const currentQ = sp.q || "";\n  const currentTime = sp.time || "all";'
)

# Data filtering logic
filter_logic = """
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
"""

c = c.replace(
    '  return (',
    filter_logic + '\n  return ('
)

# Search UI
search_ui = """      {data && (
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

      {data && ("""

c = c.replace(
    '      {data && (',
    search_ui
)

# Update array reference
c = c.replace(
    '{data.items.length} bản ghi',
    '{filteredItems.length} bản ghi'
)
c = c.replace(
    'data.items.slice(0, 1000).map',
    'filteredItems.slice(0, 1000).map'
)
c = c.replace(
    'data.items.length > 1000',
    'filteredItems.length > 1000'
)

with open(file_path, "w") as f:
    f.write(c)

print("Added filters and search to History page")
