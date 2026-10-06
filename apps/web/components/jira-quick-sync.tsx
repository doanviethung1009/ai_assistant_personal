"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { syncJiraAction } from "@/app/jira-actions";

const STORAGE_KEY = "builder_jira_configs_v2";

export function JiraQuickSync() {
  const [configs, setConfigs] = useState<any[]>([]);
  const [isSyncing, setIsSyncing] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        setConfigs(JSON.parse(saved));
      } catch (e) {}
    }
  }, []);

  if (configs.length === 0) return null;

  async function handleQuickSync() {
    setIsSyncing(true);
    const newConfigs = [...configs];
    
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
        // Cập nhật lại thời điểm sync của config này
        const idx = newConfigs.findIndex(c => c.id === config.id);
        if (idx !== -1) {
          newConfigs[idx].lastSyncAt = new Date().toISOString();
        }
      }
    }
    
    localStorage.setItem(STORAGE_KEY, JSON.stringify(newConfigs));
    setConfigs(newConfigs);
    setIsSyncing(false);
  }

  return (
    <button
      onClick={handleQuickSync}
      disabled={isSyncing}
      title="Cập nhật task mới thay đổi từ Jira"
      className="flex h-8 items-center gap-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 text-xs font-medium text-[var(--color-ink)] shadow-sm transition-colors hover:bg-[var(--color-surface-hover)] disabled:opacity-50"
    >
      <RefreshCw className={`size-3.5 ${isSyncing ? "animate-spin text-[var(--color-accent)]" : "text-[var(--color-ink-muted)]"}`} />
      {isSyncing ? "Đang kéo Jira..." : "Cập nhật Jira"}
    </button>
  );
}
