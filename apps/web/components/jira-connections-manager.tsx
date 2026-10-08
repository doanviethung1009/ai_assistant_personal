"use client";

import { useEffect, useState, useTransition } from "react";
import { AlertCircle, CheckCircle2, Clock, Edit2, KeySquare, Lock, Plus, Save, ServerCog, Trash2, UploadCloud, X } from "lucide-react";

import {
  clearIntegrationTokenAction,
  deleteIntegrationAction,
  migrateLocalIntegrationsAction,
  saveIntegrationAction,
} from "@/app/jira-actions";
import { STORAGE_KEY } from "@/lib/jira-storage";
import { formatDateTime } from "@/lib/format";
import type { IntegrationConnection } from "@/lib/types";

const INPUT =
  "w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-ink)] outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/40";

/** Phần của cấu hình cũ trong localStorage mà UI được giữ: KHÔNG gồm token. */
interface LocalLeftover {
  id: string;
  name: string;
  url: string;
  email: string;
}

interface Notice {
  ok: boolean;
  text: string;
}

/** Mục thiếu id vẫn phải hiện ra (và xoá được): dùng vị trí làm khoá thay thế. */
function leftoverKey(id: unknown, index: number): string {
  return typeof id === "string" && id ? id : `__idx${index}`;
}

function readString(v: unknown): string {
  return typeof v === "string" ? v : "";
}

/** Đọc localStorage và chỉ giữ metadata (không token) để hiện; token đọc lại lúc bấm gửi. */
function readLeftovers(): LocalLeftover[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.flatMap((item, index): LocalLeftover[] => {
      if (typeof item !== "object" || item === null) return [];
      const r = item as Record<string, unknown>;
      return [{ id: leftoverKey(r.id, index), name: readString(r.name) || "(không tên)", url: readString(r.url), email: readString(r.email) }];
    });
  } catch {
    return [];
  }
}

/**
 * Quản lý kết nối Jira lưu ở core (chế độ api, B4a).
 *
 * ══════════════════════════════════════════════════════════════════════
 *  TOKEN LÀ WRITE-ONLY. Ô token là password, autoComplete="new-password", và state
 *  của nó bị xoá NGAY khi gửi (không đợi kết quả). Danh sách chỉ hiện `****last4`. Sync
 *  thật cần pha B4b nên nút "Cào ngay" bị khoá, kèm lời giải thích.
 * ══════════════════════════════════════════════════════════════════════
 *
 * localStorage chỉ còn được đọc ở đường chuyển một lần (D-B4c): sau khi core xác nhận tạo
 * thành công thì từng mục mới bị xoá khỏi trình duyệt; mục lỗi được giữ lại để sửa tay.
 */
export function JiraConnectionsManager({ connections }: { connections: IntegrationConnection[] }) {
  const [pending, startTransition] = useTransition();
  const [editing, setEditing] = useState<IntegrationConnection | null>(null);
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [jql, setJql] = useState("");
  const [projectKey, setProjectKey] = useState("");
  const [projectName, setProjectName] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [leftovers, setLeftovers] = useState<LocalLeftover[]>([]);

  useEffect(() => {
    setLeftovers(readLeftovers());
  }, []);

  function resetForm() {
    setEditing(null);
    setName("");
    setBaseUrl("");
    setEmail("");
    setToken("");
    setJql("");
    setProjectKey("");
    setProjectName("");
  }

  function startEdit(c: IntegrationConnection) {
    setEditing(c);
    setName(c.name);
    setBaseUrl(c.base_url);
    setEmail(c.account_email);
    setToken("");
    const cfg = c.config;
    setJql(typeof cfg.jql === "string" ? cfg.jql : "");
    setProjectKey(typeof cfg.project_key === "string" ? cfg.project_key : "");
    setProjectName(typeof cfg.project_name === "string" ? cfg.project_name : "");
    setNotice(null);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setNotice(null);
    const urlChanged = editing !== null && editing.base_url !== baseUrl.trim().replace(/\/+$/, "");
    if (editing && urlChanged && editing.has_secret && !token) {
      // Core cũng từ chối (422); chặn sớm để token cũ không bị gắn sang host khác.
      setNotice({ ok: false, text: "Đổi URL Jira thì phải nhập lại token (hoặc xoá token trước)." });
      return;
    }
    if (!editing && !token) {
      setNotice({ ok: false, text: "Cần nhập token khi tạo kết nối." });
      return;
    }
    const payload = {
      id: editing?.id,
      name,
      base_url: baseUrl,
      account_email: email,
      token: token || undefined,
      jql,
      project_key: projectKey,
      project_name: projectName,
    };
    // Xoá token khỏi state TRƯỚC khi await: không để nó nằm trong React state chờ phản hồi.
    setToken("");
    startTransition(async () => {
      const res = await saveIntegrationAction(payload);
      if (res.ok) {
        setNotice({ ok: true, text: editing ? "Đã cập nhật kết nối." : "Đã tạo kết nối. Token đã được mã hoá ở server." });
        resetForm();
      } else {
        setNotice({ ok: false, text: res.error ?? "Không lưu được kết nối." });
      }
    });
  }

  function handleClearToken(c: IntegrationConnection) {
    if (!confirm(`Xoá token của "${c.name}"? Kết nối vẫn còn nhưng phải nhập token mới mới dùng được.`)) return;
    setNotice(null);
    startTransition(async () => {
      const res = await clearIntegrationTokenAction(c.id);
      setNotice(res.ok ? { ok: true, text: "Đã xoá token." } : { ok: false, text: res.error ?? "Không xoá được token." });
    });
  }

  function handleDelete(c: IntegrationConnection) {
    if (!confirm(`Xoá kết nối "${c.name}" cùng token đã mã hoá? Không hoàn tác.`)) return;
    setNotice(null);
    startTransition(async () => {
      const res = await deleteIntegrationAction(c.id);
      if (res.ok && editing?.id === c.id) resetForm();
      setNotice(res.ok ? { ok: true, text: "Đã xoá kết nối." } : { ok: false, text: res.error ?? "Không xoá được." });
    });
  }

  /** Bỏ một mục cấu hình cũ khỏi localStorage (không gửi đi đâu). Dùng cho mục chuyển lỗi. */
  function handleDiscard(key: string) {
    if (!confirm("Bỏ cấu hình này khỏi trình duyệt? Token cũ trong đó sẽ mất (không ảnh hưởng server).")) return;
    try {
      const raw: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
      const rest = Array.isArray(raw) ? raw.filter((it, i) => leftoverKey(typeof it === "object" && it !== null ? (it as Record<string, unknown>).id : undefined, i) !== key) : [];
      if (rest.length === 0) localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, JSON.stringify(rest));
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    }
    setLeftovers(readLeftovers());
  }

  function handleMigrate() {
    setNotice(null);
    // Đọc lại lúc bấm (kèm token) và chỉ giữ trong biến cục bộ, không đưa vào state.
    let items: unknown;
    try {
      items = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    } catch {
      items = [];
    }
    if (!Array.isArray(items) || items.length === 0) {
      setLeftovers([]);
      return;
    }
    startTransition(async () => {
      const res = await migrateLocalIntegrationsAction(items);
      items = undefined; // thả tham chiếu tới bản có token
      if (res.results.length === 0) {
        setNotice({ ok: false, text: res.error ?? "Không chuyển được." });
        return;
      }
      const doneIds = new Set(res.results.filter((r) => r.ok).map((r) => r.localId));
      // CHỈ xoá những mục core xác nhận đã tạo thành công.
      try {
        const raw: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
        const rest = Array.isArray(raw)
          ? raw.filter((it) => !(typeof it === "object" && it !== null && doneIds.has(readString((it as Record<string, unknown>).id))))
          : [];
        if (rest.length === 0) localStorage.removeItem(STORAGE_KEY);
        else localStorage.setItem(STORAGE_KEY, JSON.stringify(rest));
      } catch {
        /* localStorage hỏng: để nguyên, người dùng có thể xoá tay */
      }
      setLeftovers(readLeftovers());
      const failed = res.results.filter((r) => !r.ok);
      setNotice(
        failed.length === 0
          ? { ok: true, text: `Đã chuyển ${doneIds.size} kết nối lên server và xoá khỏi trình duyệt.` }
          : {
              ok: false,
              text:
                `Chuyển được ${doneIds.size}/${res.results.length}. Còn lại giữ trong trình duyệt: ` +
                failed.map((f) => `${f.name} (${f.error ?? "lỗi"})`).join("; "),
            },
      );
    });
  }

  return (
    <section className="relative overflow-hidden rounded-2xl border border-blue-500/20 bg-[var(--color-surface)] p-6 shadow-sm">
      <div className="mb-2 flex items-center gap-3">
        <div className="rounded-xl border border-blue-500/20 bg-blue-500/10 p-2.5 text-blue-500">
          <ServerCog className="size-5" />
        </div>
        <div>
          <h2 className="text-lg font-bold tracking-tight text-[var(--color-ink)]">Kết nối Jira (lưu ở server)</h2>
          <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
            Token được mã hoá ở core, chỉ ghi và không bao giờ hiện lại. Chỉ nhận <code>https://tên-miền</code> (không IP, không cổng, không path).
          </p>
        </div>
      </div>

      <p className="mt-3 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-[var(--color-ink-muted)]">
        <Lock className="mt-0.5 size-3.5 shrink-0 text-amber-500" />
        <span>
          Đồng bộ Jira từ kết nối đã lưu cần pha <b>B4b</b> (endpoint <code>/integrations/&#123;id&#125;/sync</code> chưa có), nên nút
          &ldquo;Cào ngay&rdquo; đang bị khoá. Hiện có thể lưu kết nối, và nhập task qua Excel/URL ở tab Nhập/Đồng bộ.
        </span>
      </p>

      {leftovers.length > 0 && (
        <div className="mt-4 rounded-xl border border-blue-500/30 bg-blue-500/5 p-4">
          <p className="text-sm font-semibold text-[var(--color-ink)]">
            Trình duyệt còn {leftovers.length} cấu hình Jira cũ (token đang nằm ở dạng chữ rõ trong localStorage)
          </p>
          <ul className="mt-1 text-xs text-[var(--color-ink-muted)]">
            {leftovers.map((l) => (
              <li key={l.id} className="flex items-center justify-between gap-2 py-0.5">
                <span>{l.name} · {l.url.replace(/^https?:\/\//, "")} · {l.email}</span>
                <button type="button" onClick={() => handleDiscard(l.id)} disabled={pending} className="shrink-0 rounded border border-[var(--color-border)] px-2 py-0.5 text-[11px] hover:bg-[var(--color-surface-hover)] disabled:opacity-50">
                  Bỏ khỏi trình duyệt
                </button>
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={handleMigrate}
            disabled={pending}
            className="mt-3 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-xs font-bold text-white hover:bg-blue-700 disabled:opacity-50"
          >
            <UploadCloud className="size-4" /> Chuyển các kết nối này lên server
          </button>
          <p className="mt-2 text-[11px] text-[var(--color-ink-muted)]">
            Gửi một lần; chỉ mục nào server tạo thành công mới bị xoá khỏi trình duyệt.
          </p>
        </div>
      )}

      {connections.length > 0 && (
        <div className="mb-6 mt-6">
          <h3 className="mb-3 text-sm font-semibold">Các kết nối đã lưu ({connections.length})</h3>
          <div className="grid gap-3">
            {connections.map((c) => (
              <div key={c.id} className="flex flex-col justify-between gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 md:flex-row md:items-center">
                <div className="min-w-0">
                  <p className="text-sm font-bold text-[var(--color-ink)]">{c.name}</p>
                  <p className="mt-1 break-all text-xs text-[var(--color-ink-muted)]">
                    {c.base_url} · {c.account_email}
                  </p>
                  <p className="mt-1 flex items-center gap-1 text-xs text-[var(--color-ink-muted)]">
                    <KeySquare className="size-3" />
                    {c.has_secret ? `Token: ****${c.secret_last4 ?? ""}` : "Chưa có token"}
                    <span className="mx-1 opacity-40">•</span>
                    <Clock className="size-3" />
                    {c.last_sync_at ? `Đồng bộ lần cuối: ${formatDateTime(c.last_sync_at)}` : "Chưa đồng bộ"}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    disabled
                    title="Cần pha B4b (endpoint sync phía core chưa có)"
                    className="cursor-not-allowed rounded-lg bg-[var(--color-surface)] px-3 py-2 text-xs font-bold text-[var(--color-ink-muted)] opacity-60 border border-[var(--color-border)]"
                  >
                    Cào ngay (cần B4b)
                  </button>
                  <button type="button" onClick={() => startEdit(c)} disabled={pending} aria-label={`Sửa ${c.name}`} className="rounded-lg p-2 text-[var(--color-ink-muted)] hover:bg-blue-500/10 hover:text-blue-500 disabled:opacity-50">
                    <Edit2 className="size-4" />
                  </button>
                  {c.has_secret && (
                    <button type="button" onClick={() => handleClearToken(c)} disabled={pending} className="rounded-lg border border-[var(--color-border)] px-3 py-2 text-xs font-medium hover:bg-[var(--color-surface-hover)] disabled:opacity-50">
                      Xoá token
                    </button>
                  )}
                  <button type="button" onClick={() => handleDelete(c)} disabled={pending} aria-label={`Xoá ${c.name}`} className="rounded-lg p-2 text-[var(--color-ink-muted)] hover:bg-red-500/10 hover:text-red-500 disabled:opacity-50">
                    <Trash2 className="size-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <details open={connections.length === 0 || editing !== null} className="mt-4">
        <summary className="flex w-max cursor-pointer select-none items-center gap-2 text-sm font-bold text-blue-500 hover:text-blue-600">
          {editing ? <><Edit2 className="size-4" /> Sửa kết nối</> : <><Plus className="size-4" /> Thêm kết nối Jira mới</>}
        </summary>
        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-5">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="text-xs font-bold">
              Tên gợi nhớ
              <input className={`${INPUT} mt-1.5 font-normal`} required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} placeholder="VD: Dự án SRE Công ty" />
            </label>
            <label className="text-xs font-bold">
              URL Jira
              <input className={`${INPUT} mt-1.5 font-normal`} required type="url" maxLength={2048} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://yourdomain.atlassian.net" />
            </label>
            <label className="text-xs font-bold">
              Email đăng nhập
              <input className={`${INPUT} mt-1.5 font-normal`} required type="email" maxLength={200} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" />
            </label>
            <label className="text-xs font-bold">
              <span className="flex items-center justify-between">
                Jira API Token
                <a href="https://id.atlassian.com/manage-profile/security/api-tokens" target="_blank" rel="noreferrer" className="text-[10px] font-medium text-blue-500 hover:underline">Lấy token ở đâu?</a>
              </span>
              <input
                className={`${INPUT} mt-1.5 font-normal`}
                type="password"
                autoComplete="new-password"
                minLength={8}
                maxLength={512}
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder={editing?.has_secret ? `Để trống = giữ token cũ (****${editing.secret_last4 ?? ""})` : "ATATT3xFfGF..."}
              />
            </label>
            <label className="text-xs font-bold">
              Mã dự án gắn vào task (tuỳ chọn)
              <input className={`${INPUT} mt-1.5 font-mono font-normal uppercase`} maxLength={100} value={projectKey} onChange={(e) => setProjectKey(e.target.value)} placeholder="SRE" />
            </label>
            <label className="text-xs font-bold">
              Tên dự án (tuỳ chọn)
              <input className={`${INPUT} mt-1.5 font-normal`} maxLength={200} value={projectName} onChange={(e) => setProjectName(e.target.value)} placeholder="Tên dự án đầy đủ" />
            </label>
          </div>
          <label className="text-xs font-bold">
            JQL (bộ lọc Jira, tuỳ chọn)
            <textarea className={`${INPUT} mt-1.5 h-20 resize-none font-mono text-[13px] font-normal`} maxLength={2000} value={jql} onChange={(e) => setJql(e.target.value)} placeholder="Để trống = task giao cho bạn" />
          </label>
          <div className="flex gap-3">
            <button type="submit" disabled={pending} className="flex items-center gap-2 rounded-lg bg-[var(--color-ink)] px-5 py-2 text-sm font-bold text-[var(--color-surface)] hover:opacity-90 disabled:opacity-50">
              <Save className="size-4" />
              {pending ? "Đang lưu..." : editing ? "Cập nhật kết nối" : "Lưu kết nối"}
            </button>
            {editing && (
              <button type="button" onClick={resetForm} className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-2 text-sm font-bold hover:bg-[var(--color-surface-hover)]">
                <X className="size-4" /> Hủy sửa
              </button>
            )}
          </div>
        </form>
      </details>

      {notice && (
        <div
          role="status"
          className={`mt-5 flex items-start gap-3 rounded-xl border p-4 text-sm ${
            notice.ok
              ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
              : "border-red-500/20 bg-red-500/10 text-red-700 dark:text-red-400"
          }`}
        >
          {notice.ok ? <CheckCircle2 className="mt-0.5 size-5 shrink-0" /> : <AlertCircle className="mt-0.5 size-5 shrink-0" />}
          <p className="break-words">{notice.text}</p>
        </div>
      )}
    </section>
  );
}
