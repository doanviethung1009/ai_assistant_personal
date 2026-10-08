"use client";

import { useEffect, useState, useTransition } from "react";
import { syncJiraAction } from "@/app/jira-actions";
import { STORAGE_KEY } from "@/lib/jira-storage";
import { RefreshCw, ServerCog, Edit2, Trash2, CheckCircle2, AlertCircle, Save, X, Plus, Clock, KeySquare, Mail, Link as LinkIcon, FolderKanban, TerminalSquare } from "lucide-react";



export interface JiraConfig {
  id: string;
  name: string;
  url: string;
  email: string;
  token: string;
  jql: string;
  projectKey?: string;
  projectName?: string;
  lastSyncAt?: string;
}

export function JiraSyncManager({ projects = [], taskCount = 0 }: { projects?: { id: string; key: string; name: string }[], taskCount?: number }) {
  const [configs, setConfigs] = useState<JiraConfig[]>([]);
  const [isLoaded, setIsLoaded] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Form states
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [jql, setJql] = useState("");
  const [projectKey, setProjectKey] = useState("");
  const [projectName, setProjectName] = useState("");

  const [result, setResult] = useState<{ ok: boolean; added?: number; updated?: number; skipped_personal?: number; error?: string } | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [pendingMode, setPendingMode] = useState<string>("30d");
  const [syncRange, setSyncRange] = useState<Record<string, string>>({});

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        setConfigs(JSON.parse(saved));
      } catch (e) {}
    }
    setIsLoaded(true);
  }, []);

  function saveToStorage(newConfigs: JiraConfig[]) {
    setConfigs(newConfigs);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(newConfigs));
  }

  function handleSaveConfig(e: React.FormEvent) {
    e.preventDefault();
    if (!name || !url || !email || !token) return;

    let newConfigs = [...configs];
    if (editingId) {
      newConfigs = newConfigs.map(c => c.id === editingId ? { ...c, name, url, email, token, jql, projectKey: projectKey === "NEW" ? "" : projectKey.trim().toUpperCase(), projectName: projectName.trim() } : c);
    } else {
      newConfigs.push({
        id: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(),
        name,
        url,
        email,
        token,
        jql,
        projectKey: projectKey === "NEW" ? "" : projectKey.trim().toUpperCase(),
        projectName: projectName.trim()
      });
    }

    saveToStorage(newConfigs);
    resetForm();
    alert("Đã lưu cấu hình Jira vào trình duyệt!");
  }

  function handleEdit(c: JiraConfig) {
    setEditingId(c.id);
    setName(c.name);
    setUrl(c.url);
    setEmail(c.email);
    setToken(c.token);
    setJql(c.jql);
    setProjectKey(c.projectKey || "");
    setProjectName(c.projectName || "");
  }

  function handleDelete(id: string) {
    if (!confirm("Bạn có chắc chắn muốn xoá cấu hình này khỏi trình duyệt?")) return;
    saveToStorage(configs.filter(c => c.id !== id));
    if (editingId === id) resetForm();
  }

  function resetForm() {
    setEditingId(null);
    setName("");
    setUrl("");
    setEmail("");
    setToken("");
    setJql("");
    setProjectKey("");
    setProjectName("");
  }

  async function handleSync(config: JiraConfig, mode: string = "30d") {
    setResult(null);
    setPendingId(config.id);
    setPendingMode(mode);

    const fd = new FormData();
    fd.append("url", config.url);
    fd.append("email", config.email);
    fd.append("token", config.token);
    fd.append("jql", config.jql);
    fd.append("projectKey", config.projectKey || "");
    fd.append("projectName", config.projectName || "");
    
    if (mode === "update" && config.lastSyncAt) {
      fd.append("since", config.lastSyncAt);
    } else if (mode === "1d") {
      fd.append("since", new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString());
    } else if (mode === "3d") {
      fd.append("since", new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString());
    } else if (mode === "7d") {
      fd.append("since", new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString());
    } else if (mode === "30d") {
      fd.append("since", new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString());
    }

    const response = await syncJiraAction(fd);
    setResult(response);
    if (response.ok) {
      // Ghi lại mốc đồng bộ
      saveToStorage(
        configs.map(c => (c.id === config.id ? { ...c, lastSyncAt: new Date().toISOString() } : c))
      );
    }
    setPendingId(null);
  }

  if (!isLoaded) return <div className="h-40 animate-pulse bg-[var(--color-surface-raised)] border border-[var(--color-border)] rounded-xl mt-6"></div>;

  return (
    <section className="relative overflow-hidden rounded-2xl border border-blue-500/20 bg-gradient-to-br from-[var(--color-surface-raised)] to-[var(--color-surface)] p-1">
      {/* Decorative background glow */}
      <div className="absolute top-0 right-0 -mr-20 -mt-20 h-64 w-64 rounded-full bg-blue-500/10 blur-3xl pointer-events-none"></div>
      
      <div className="relative bg-[var(--color-surface)] m-0.5 rounded-xl p-6 shadow-sm border border-[var(--color-border)]">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2.5 bg-blue-500/10 text-blue-500 rounded-xl shadow-sm border border-blue-500/20">
            <ServerCog className="size-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold tracking-tight text-[var(--color-ink)]">Đồng bộ từ Jira (Trực tiếp)</h2>
            <p className="text-xs text-[var(--color-ink-muted)] mt-0.5">
              Kết nối trực tiếp tới Jira Cloud bằng API Token. Dữ liệu lưu an toàn trên máy bạn.
            </p>
          </div>
        </div>

        {/* Danh sách cấu hình */}
        {configs.length > 0 && (
          <div className="mt-6 mb-8">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> 
              Các kết nối đã lưu
            </h3>
            <div className="grid gap-4">
              {configs.map(c => (
                <div key={c.id} className="group flex flex-col md:flex-row md:items-center justify-between p-4 rounded-xl bg-[var(--color-surface-raised)] border border-[var(--color-border)] shadow-sm hover:border-blue-500/30 hover:shadow-md transition-all duration-300">
                  <div className="mb-4 md:mb-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-bold text-[var(--color-ink)]">{c.name}</p>
                      {c.projectKey && (
                        <span className="rounded-md bg-indigo-500/10 px-2 py-0.5 text-[10px] font-bold text-indigo-600 border border-indigo-500/20 shadow-sm flex items-center gap-1">
                          <FolderKanban className="size-3" /> {c.projectKey}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-[var(--color-ink-muted)] mt-1.5 flex items-center gap-2">
                      <span className="flex items-center gap-1"><Mail className="size-3" /> {c.email}</span>
                      <span className="opacity-40">•</span>
                      <span className="flex items-center gap-1"><LinkIcon className="size-3" /> {c.url.replace(/^https?:\/\//, '')}</span>
                    </p>
                    {c.lastSyncAt && (
                      <p className="text-[10px] text-[var(--color-ink-muted)] mt-1.5 flex items-center gap-1 font-medium">
                        <Clock className="size-3 text-emerald-500" /> Đồng bộ lần cuối: {new Date(c.lastSyncAt).toLocaleString("vi-VN")}
                      </p>
                    )}
                  </div>
                  
                  <div className="flex flex-wrap gap-2 items-center">
                    {c.lastSyncAt && taskCount > 0 && (
                      <button
                        onClick={() => handleSync(c, "update")}
                        disabled={pendingId !== null}
                        title={`Chỉ lấy task thay đổi từ ${new Date(c.lastSyncAt).toLocaleString("vi-VN")}`}
                        className="flex items-center gap-1.5 text-xs font-bold bg-gradient-to-r from-emerald-500 to-teal-600 text-white px-4 py-2 rounded-lg hover:from-emerald-600 hover:to-teal-700 shadow-sm hover:shadow transition-all disabled:opacity-50"
                      >
                        <RefreshCw className={`size-3.5 ${pendingId === c.id && pendingMode === "update" ? "animate-spin" : ""}`} />
                        {pendingId === c.id && pendingMode === "update" ? "Đang kéo..." : "Cập nhật nhanh"}
                      </button>
                    )}
                    
                    <div className="flex items-center border border-[var(--color-border)] rounded-lg overflow-hidden bg-[var(--color-surface)] shadow-sm focus-within:ring-2 focus-within:ring-blue-500/30 transition-all">
                      <select 
                         value={syncRange[c.id] || "3d"}
                         onChange={(e) => setSyncRange(prev => ({...prev, [c.id]: e.target.value}))}
                         className="text-xs bg-transparent pl-3 pr-2 py-2 font-medium focus:outline-none cursor-pointer text-[var(--color-ink)]"
                         disabled={pendingId !== null}
                      >
                        <option value="1d">1 ngày</option>
                        <option value="3d">3 ngày</option>
                        <option value="7d">7 ngày</option>
                        <option value="30d">30 ngày</option>
                        <option value="all">Tất cả (Chậm)</option>
                      </select>
                      <button 
                        onClick={() => {
                          const range = syncRange[c.id] || "3d";
                          if (range === "all" && !confirm("Kéo toàn bộ lịch sử có thể mất vài phút. Bạn có chắc chắn?")) return;
                          handleSync(c, range);
                        }} 
                        disabled={pendingId !== null}
                        className="text-xs font-bold bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400 px-4 py-2 hover:bg-blue-100 dark:hover:bg-blue-500/20 disabled:opacity-50 transition-colors border-l border-[var(--color-border)]"
                      >
                        {pendingId === c.id && pendingMode !== "update" ? "Đang xử lý..." : "Đồng bộ"}
                      </button>
                    </div>

                    <div className="flex items-center gap-1 ml-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => handleEdit(c)} className="p-2 text-[var(--color-ink-muted)] hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-500/10 rounded-lg transition-colors">
                        <Edit2 className="size-4" />
                      </button>
                      <button onClick={() => handleDelete(c.id)} className="p-2 text-[var(--color-ink-muted)] hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-lg transition-colors">
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Form thêm/sửa cấu hình */}
        <details open={configs.length === 0 || editingId !== null} className="group">
          <summary className="flex cursor-pointer items-center gap-2 text-sm font-bold select-none text-blue-500 hover:text-blue-600 transition-colors w-max">
            {editingId ? <><Edit2 className="size-4" /> Sửa kết nối</> : <><Plus className="size-4" /> Thêm kết nối Jira mới</>}
          </summary>
          
          <form onSubmit={handleSaveConfig} className="mt-4 flex flex-col gap-5 p-5 bg-[var(--color-surface-raised)] border border-[var(--color-border)] rounded-xl shadow-inner">
            <div className="grid md:grid-cols-2 gap-5">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-[var(--color-ink)]">Tên gợi nhớ</label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[var(--color-ink-muted)]">
                    <ServerCog className="size-4" />
                  </div>
                  <input
                    type="text"
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="VD: Dự án SRE Công ty"
                    className="w-full pl-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-ink)] focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 outline-none transition-all shadow-sm"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-[var(--color-ink)]">URL Jira</label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[var(--color-ink-muted)]">
                    <LinkIcon className="size-4" />
                  </div>
                  <input
                    type="url"
                    required
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    placeholder="https://yourdomain.atlassian.net"
                    className="w-full pl-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-ink)] focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 outline-none transition-all shadow-sm"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-[var(--color-ink)]">Email đăng nhập</label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[var(--color-ink-muted)]">
                    <Mail className="size-4" />
                  </div>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@company.com"
                    className="w-full pl-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-ink)] focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 outline-none transition-all shadow-sm"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-[var(--color-ink)] flex items-center justify-between">
                  <span>Jira API Token</span>
                  <a href="https://id.atlassian.com/manage-profile/security/api-tokens" target="_blank" rel="noreferrer" className="text-[10px] text-blue-500 hover:underline font-medium">Lấy token ở đâu?</a>
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[var(--color-ink-muted)]">
                    <KeySquare className="size-4" />
                  </div>
                  <input
                    type="password"
                    required
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    placeholder="ATATT3xFfGF..."
                    className="w-full pl-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-ink)] focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 outline-none transition-all shadow-sm"
                  />
                </div>
              </div>
            </div>

            <div className="h-px bg-[var(--color-border)]/50 my-1"></div>

            <div className="grid md:grid-cols-2 gap-5">
              <div>
                <label className="mb-1.5 block text-xs font-bold text-[var(--color-ink)]">Dự án hệ thống (Gắn vào task)</label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[var(--color-ink-muted)]">
                    <FolderKanban className="size-4" />
                  </div>
                  <select
                    value={projects.some(p => p.key === projectKey) ? projectKey : projectKey ? "__new__" : ""}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (v === "") { setProjectKey(""); setProjectName(""); }
                      else if (v === "__new__") { setProjectKey("NEW"); setProjectName(""); }
                      else { setProjectKey(v); setProjectName(projects.find(p => p.key === v)?.name || ""); }
                    }}
                    className="w-full pl-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-ink)] focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 outline-none transition-all shadow-sm appearance-none"
                  >
                    <option value="">— Trống (Không tự động phân loại) —</option>
                    {projects.map(p => (<option key={p.id} value={p.key}>{p.key} · {p.name}</option>))}
                    <option value="__new__">➕ Tạo dự án mới…</option>
                  </select>
                </div>
                {projectKey && !projects.some(p => p.key === projectKey) && (
                  <div className="mt-3 flex gap-2 p-3 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg shadow-inner">
                    <input
                      type="text"
                      value={projectKey === "NEW" ? "" : projectKey}
                      onChange={(e) => setProjectKey(e.target.value.toUpperCase() || "NEW")}
                      placeholder="Mã dự án"
                      pattern="[A-Za-z][A-Za-z0-9_]{1,19}"
                      className="w-1/3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-1.5 text-sm uppercase text-[var(--color-ink)] focus:ring-1 focus:ring-blue-500 outline-none font-mono"
                    />
                    <input
                      type="text"
                      value={projectName}
                      onChange={(e) => setProjectName(e.target.value)}
                      placeholder="Tên dự án đầy đủ"
                      className="w-2/3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-1.5 text-sm text-[var(--color-ink)] focus:ring-1 focus:ring-blue-500 outline-none"
                    />
                  </div>
                )}
                <p className="text-[10px] text-[var(--color-ink-muted)] mt-2 font-medium">
                  Mọi task kéo về từ cấu hình này sẽ tự động được link vào dự án bạn chọn.
                </p>
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-bold text-[var(--color-ink)] flex items-center gap-1.5">
                  <TerminalSquare className="size-4 text-[var(--color-ink-muted)]" />
                  JQL (Bộ lọc Jira)
                </label>
                <textarea
                  value={jql}
                  onChange={(e) => setJql(e.target.value)}
                  placeholder='VD: project = "SRE"&#10;Để trống = Tự động lấy task assign cho bạn'
                  className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-[13px] font-mono text-[var(--color-ink)] h-20 resize-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 outline-none shadow-inner"
                />
              </div>
            </div>

            <div className="pt-3 flex gap-3">
              <button
                type="submit"
                className="flex items-center gap-2 rounded-lg bg-[var(--color-ink)] px-5 py-2 text-sm font-bold text-[var(--color-surface)] hover:opacity-90 transition-opacity shadow-sm"
              >
                <Save className="size-4" />
                {editingId ? "Cập nhật cấu hình" : "Lưu cấu hình mới"}
              </button>
              {editingId && (
                <button
                  type="button"
                  onClick={resetForm}
                  className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-2 text-sm font-bold text-[var(--color-ink)] hover:bg-[var(--color-surface-hover)] transition-colors shadow-sm"
                >
                  <X className="size-4" />
                  Hủy sửa
                </button>
              )}
            </div>
          </form>
        </details>

        {result && (
          <div className={`mt-6 p-4 rounded-xl flex items-start gap-3 border shadow-sm ${
            result.ok 
              ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20' 
              : 'bg-red-500/10 text-red-700 dark:text-red-400 border-red-500/20'
          }`}>
            {result.ok ? <CheckCircle2 className="size-5 shrink-0 mt-0.5 text-emerald-500" /> : <AlertCircle className="size-5 shrink-0 mt-0.5 text-red-500" />}
            <div>
              <p className="font-bold">{result.ok ? "Đồng bộ thành công!" : "Lỗi đồng bộ"}</p>
              <p className="text-sm mt-1 opacity-90">
                {result.ok 
                  ? `Hệ thống đã kéo về và tự động tạo mới ${result.added} task, cập nhật lại ${result.updated} task.` +
                    (result.skipped_personal
                      ? ` Bỏ qua ${result.skipped_personal} task cá nhân (đã tách khỏi đồng bộ).`
                      : "")
                  : result.error}
              </p>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
