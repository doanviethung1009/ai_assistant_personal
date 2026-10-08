"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { syncJiraAction } from "@/app/jira-actions";
import { useRouter } from "next/navigation";

const STORAGE_KEY = "builder_jira_configs_v2";

export function JiraQuickSync() {
  const router = useRouter();
  const [configs, setConfigs] = useState<any[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState<"idle" | "success" | "error">("idle");
  const [lastSyncText, setLastSyncText] = useState<string>("");
  // Số task cá nhân bị bỏ qua ở lần đồng bộ gần nhất (0 thì không hiện).
  const [skippedNote, setSkippedNote] = useState(0);

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setConfigs(parsed);
        if (parsed.length > 0 && parsed[0].lastSyncAt) {
          const d = new Date(parsed[0].lastSyncAt);
          setLastSyncText(d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }));
        }
      } catch (e) {}
    }
  }, []);

  if (configs.length === 0) return null;

  async function handleQuickSync() {
    setIsSyncing(true);
    setSyncStatus("idle");
    const newConfigs = [...configs];
    let hasError = false;
    let syncedCount = 0;
    let skippedPersonal = 0;
    const nowIso = new Date().toISOString();
    
    for (const config of configs) {
      const fd = new FormData();
      fd.append("url", config.url);
      fd.append("email", config.email);
      fd.append("token", config.token);
      fd.append("jql", config.jql);
      fd.append("projectKey", config.projectKey || "");
      fd.append("projectName", config.projectName || "");
      if (config.lastSyncAt) {
        fd.append("since", config.lastSyncAt);
      } else {
        fd.append("since", new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString());
      }

      const response = await syncJiraAction(fd);
      if (response.ok) {
        syncedCount++;
        if ("skipped_personal" in response) skippedPersonal += response.skipped_personal ?? 0;
        const idx = newConfigs.findIndex(c => c.id === config.id);
        if (idx !== -1) {
          newConfigs[idx].lastSyncAt = nowIso;
        }
      } else {
        hasError = true;
      }
    }
    
    localStorage.setItem(STORAGE_KEY, JSON.stringify(newConfigs));
    setConfigs(newConfigs);
    
    const d = new Date(nowIso);
    setLastSyncText(d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }));
    setIsSyncing(false);
    setSkippedNote(skippedPersonal);

    if (hasError && syncedCount === 0) {
      setSyncStatus("error");
      alert("Đồng bộ Jira thất bại! Hãy kiểm tra lại kết nối hoặc cấu hình trong trang Dữ liệu.");
    } else {
      setSyncStatus("success");
      // Dùng Next.js router để refresh data ngầm (soft reload) mà không chớp trang
      router.refresh();
    }
    
    setTimeout(() => {
      setSyncStatus("idle");
    }, 3000);
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={handleQuickSync}
        disabled={isSyncing}
        title="Cập nhật task mới thay đổi từ Jira"
        className={`flex h-8 items-center gap-1.5 rounded-md border px-3 text-xs font-medium shadow-sm transition-all disabled:opacity-70 ${
          syncStatus === "success"
            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
            : syncStatus === "error"
            ? "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400"
            : "border-[var(--color-border)] bg-[var(--color-surface-raised)] text-[var(--color-ink)] hover:bg-[var(--color-surface-hover)] hover:border-blue-500/30 hover:text-blue-500"
        }`}
      >
        <RefreshCw className={`size-3.5 ${
          isSyncing 
            ? "animate-spin text-blue-500" 
            : syncStatus === "success"
            ? "text-emerald-500"
            : syncStatus === "error"
            ? "text-red-500"
            : "text-[var(--color-ink-muted)] group-hover:text-blue-500"
        }`} />
        {isSyncing 
          ? "Đang kéo Jira..." 
          : syncStatus === "success" 
          ? "Đã đồng bộ!" 
          : syncStatus === "error"
          ? "Lỗi đồng bộ"
          : "Cập nhật Jira"}
      </button>
      
      {skippedNote > 0 && !isSyncing && (
        <span className="text-[10px] text-[var(--color-ink-muted)] mr-1">
          Bỏ qua {skippedNote} task cá nhân
        </span>
      )}

      {lastSyncText && !isSyncing && syncStatus !== "success" && (
        <span className="text-[10px] text-[var(--color-ink-muted)] mr-1">
          Lần cuối: {lastSyncText}
        </span>
      )}
    </div>
  );
}
