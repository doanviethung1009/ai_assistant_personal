"use client";

import { useEffect, useState, useTransition } from "react";
import { syncJiraAction } from "@/app/jira-actions";
import { uuid } from "@/lib/store/engine"; // Hoặc có thể import 1 hàm uuid đơn giản

const STORAGE_KEY = "builder_jira_configs_v2";

export interface JiraConfig {
  id: string;
  name: string;
  url: string;
  email: string;
  token: string;
  jql: string;
}

export function JiraSyncManager() {
  const [configs, setConfigs] = useState<JiraConfig[]>([]);
  const [isLoaded, setIsLoaded] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Form states
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [jql, setJql] = useState("");

  const [result, setResult] = useState<{ ok: boolean; added?: number; updated?: number; error?: string } | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [isFormPending, startFormTransition] = useTransition();

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
      newConfigs = newConfigs.map(c => c.id === editingId ? { id: c.id, name, url, email, token, jql } : c);
    } else {
      newConfigs.push({
        id: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(),
        name,
        url,
        email,
        token,
        jql
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
  }

  async function handleSync(config: JiraConfig) {
    setResult(null);
    setPendingId(config.id);

    const fd = new FormData();
    fd.append("url", config.url);
    fd.append("email", config.email);
    fd.append("token", config.token);
    fd.append("jql", config.jql);

    const response = await syncJiraAction(fd);
    setResult(response);
    setPendingId(null);
  }

  if (!isLoaded) return <div className="h-40 animate-pulse bg-gray-100 dark:bg-gray-800 rounded-lg mt-6"></div>;

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 mt-6">
      <h2 className="text-sm font-semibold">Đồng bộ từ Jira (Trực tiếp)</h2>
      <p className="mt-1 text-xs text-[var(--color-ink-muted)] mb-4">
        Lưu nhiều cấu hình kết nối Jira khác nhau. Cấu hình được lưu trữ an toàn trong Local Storage của trình duyệt.
        Để lấy toàn bộ task của team, bạn chỉ cần đặt JQL là <code>project = "MÃ_DỰ_ÁN"</code> (Ví dụ: <code>project = "SRE"</code>).
      </p>

      {/* Danh sách cấu hình */}
      {configs.length > 0 && (
        <div className="mb-6 border-b border-[var(--color-border)] pb-6">
          <h3 className="text-sm font-medium mb-3">Các cấu hình đã lưu:</h3>
          <div className="grid gap-3">
            {configs.map(c => (
              <div key={c.id} className="flex items-center justify-between p-3 rounded-md bg-[var(--color-surface)] border border-[var(--color-border)]">
                <div>
                  <p className="text-sm font-medium">{c.name}</p>
                  <p className="text-xs text-[var(--color-ink-muted)]">{c.email} &bull; {c.url}</p>
                </div>
                <div className="flex gap-2 items-center">
                  <button 
                    onClick={() => handleSync(c)} 
                    disabled={pendingId !== null}
                    className="text-xs font-medium bg-[var(--color-accent)] text-white px-3 py-1.5 rounded-md hover:bg-blue-600 disabled:opacity-50"
                  >
                    {pendingId === c.id ? "Đang kéo..." : "Đồng bộ"}
                  </button>
                  <button onClick={() => handleEdit(c)} className="text-xs font-medium text-[var(--color-ink)] bg-gray-100 dark:bg-gray-800 px-3 py-1.5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700">
                    Sửa
                  </button>
                  <button onClick={() => handleDelete(c.id)} className="text-xs font-medium text-red-600 bg-red-50 dark:bg-red-900/20 px-3 py-1.5 rounded-md hover:bg-red-100 dark:hover:bg-red-900/40">
                    Xoá
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Form thêm/sửa cấu hình */}
      <div>
        <h3 className="text-sm font-medium mb-3">{editingId ? "Sửa cấu hình Jira" : "Thêm cấu hình Jira mới"}</h3>
        <form onSubmit={handleSaveConfig} className="flex flex-col gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--color-ink-muted)]">
              Tên cấu hình
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="VD: Dự án SRE Công ty"
              className="w-full max-w-md rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm text-[var(--color-ink)]"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--color-ink-muted)]">
              URL Jira
            </label>
            <input
              type="url"
              required
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://yourdomain.atlassian.net"
              className="w-full max-w-md rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm text-[var(--color-ink)]"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--color-ink-muted)]">
              Email tài khoản
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@company.com"
              className="w-full max-w-md rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm text-[var(--color-ink)]"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--color-ink-muted)]">
              Jira API Token
            </label>
            <input
              type="password"
              required
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="ATATT3xFfGF..."
              className="w-full max-w-md rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm text-[var(--color-ink)]"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--color-ink-muted)]">
              Câu lệnh JQL (Tùy chọn)
            </label>
            <textarea
              value={jql}
              onChange={(e) => setJql(e.target.value)}
              placeholder='VD: project = "SRE"&#10;(Nếu để trống, mặc định lấy task assign cho bạn)'
              className="w-full max-w-md rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm text-[var(--color-ink)] h-16 resize-none"
            />
            <p className="text-[10px] text-[var(--color-ink-muted)] mt-1 max-w-md">
              Mẹo: Lấy toàn bộ task của team bằng JQL <code>project = "MÃ_DỰ_ÁN"</code>. Hoặc lấy task của team + task của mình: <code>project = "SRE" OR assignee = currentUser()</code>.
            </p>
          </div>

          <div className="pt-2 flex gap-3">
            <button
              type="submit"
              className="rounded-md bg-gray-800 px-4 py-2 text-sm font-medium text-white hover:bg-gray-900 dark:bg-gray-200 dark:text-gray-900 dark:hover:bg-gray-300"
            >
              {editingId ? "Cập nhật cấu hình" : "Lưu cấu hình mới"}
            </button>
            {editingId && (
              <button
                type="button"
                onClick={resetForm}
                className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2 text-sm font-medium text-[var(--color-ink)] hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                Hủy
              </button>
            )}
          </div>
        </form>
      </div>

      {result && (
        <div className={`mt-6 p-3 rounded-md text-sm ${result.ok ? 'bg-green-500/10 text-green-600 border border-green-500/20' : 'bg-red-500/10 text-red-600 border border-red-500/20'}`}>
          {result.ok ? (
            <p>✅ Thành công! Đã thêm mới {result.added} và cập nhật {result.updated} task.</p>
          ) : (
            <p>❌ {result.error}</p>
          )}
        </div>
      )}
    </section>
  );
}
