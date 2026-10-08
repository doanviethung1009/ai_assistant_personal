"use client";

import { useState, useTransition, useEffect } from "react";
import { syncChromeHistoryAction, listChromeProfilesAction, deleteChromeHistoryAction } from "@/app/actions-chrome";

interface ProfileInfo {
  folder: string;
  name: string;
  email: string;
  historyPath: string;
  hasHistory: boolean;
}

export function ChromeHistoryManager() {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [customPath, setCustomPath] = useState("");
  const [showPathInput, setShowPathInput] = useState(false);
  const [profiles, setProfiles] = useState<ProfileInfo[]>([]);
  const [loadingProfiles, setLoadingProfiles] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState("");

  /** Tải danh sách Chrome profile từ máy */
  const loadProfiles = async () => {
    setLoadingProfiles(true);
    const res = await listChromeProfilesAction();
    if (res.ok && res.profiles) {
      setProfiles(res.profiles as ProfileInfo[]);
    }
    setLoadingProfiles(false);
  };

  /** Khi chọn profile từ dropdown, tự điền đường dẫn History */
  const handleProfileSelect = (value: string) => {
    setSelectedProfile(value);
    if (value) {
      const profile = profiles.find(p => p.folder === value);
      if (profile) {
        setCustomPath(profile.historyPath);
      }
    } else {
      setCustomPath("");
    }
  };

  const handleSync = () => {
    setResult(null);
    startTransition(async () => {
      const pathToUse = customPath.trim() || undefined;
      const res = await syncChromeHistoryAction(5000, pathToUse);
      if (res.ok) {
        const where = res.pushed
          ? `Đã đẩy lên Postgres (profile ${res.profile}): ${res.pushed.created} mới, ${res.pushed.updated} cập nhật, ${res.pushed.unchanged} không đổi, ${res.pushed.invalid} bỏ qua.`
          : `Lưu tại: ${res.path}`;
        setResult({ ok: true, message: `Thành công! Đã trích xuất ${res.count} dòng lịch sử web. ${where}` });
      } else {
        setResult({ ok: false, message: `Lỗi: ${res.error}` });
      }
    });
  };

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 mt-6">
      <h2 className="text-sm font-semibold">Đồng bộ Lịch sử Google Chrome</h2>
      <p className="mt-1 text-xs text-[var(--color-ink-muted)] mb-3">
        Tự động copy dữ liệu lịch sử duyệt web (Google Chrome) trên máy tính này và trích xuất rồi lưu: ở chế độ file thành <code>data/chrome-history.json</code>, ở chế độ api đẩy lên Postgres theo từng profile.
      </p>

      {/* Chọn Chrome Profile */}
      <div className="mb-3 flex flex-col gap-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
        <div className="flex items-center justify-between">
          <label className="text-xs font-medium">Chọn Chrome Profile:</label>
          <button
            type="button"
            onClick={loadProfiles}
            disabled={loadingProfiles}
            className="text-xs text-[var(--color-accent)] hover:underline disabled:opacity-50"
          >
            {loadingProfiles ? "Đang tải..." : profiles.length > 0 ? "↻ Tải lại" : "Quét danh sách profile"}
          </button>
        </div>

        {profiles.length > 0 ? (
          <select
            value={selectedProfile}
            onChange={(e) => handleProfileSelect(e.target.value)}
            className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm"
          >
            <option value="">— Mặc định (Default) —</option>
            {profiles.map((p) => (
              <option key={p.folder} value={p.folder} disabled={!p.hasHistory}>
                {p.name} — {p.email || "(chưa đăng nhập)"} {!p.hasHistory ? "(không có History)" : ""}
              </option>
            ))}
          </select>
        ) : (
          <p className="text-[11px] text-[var(--color-ink-muted)]">
            Bấm <b>&quot;Quét danh sách profile&quot;</b> để hiển thị tất cả Chrome profile (kèm email) trên máy.
          </p>
        )}

        {selectedProfile && (
          <p className="text-[10px] font-mono text-[var(--color-ink-muted)] break-all">
            📁 {customPath}
          </p>
        )}
      </div>

      {/* Nút toggle hiển thị ô nhập đường dẫn tuỳ chỉnh */}
      <button
        type="button"
        onClick={() => setShowPathInput(!showPathInput)}
        className="mb-3 text-xs text-[var(--color-ink-muted)] hover:text-[var(--color-accent)] hover:underline"
      >
        {showPathInput ? "▾ Ẩn nhập đường dẫn thủ công" : "▸ Nhập đường dẫn thủ công (nâng cao)"}
      </button>

      {showPathInput && (
        <div className="mb-3 flex flex-col gap-2 rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] p-3">
          <label className="text-xs font-medium text-[var(--color-ink-muted)]">
            Đường dẫn tới file <code>History</code> của Chrome:
          </label>
          <input
            type="text"
            value={customPath}
            onChange={(e) => { setCustomPath(e.target.value); setSelectedProfile(""); }}
            placeholder="Ví dụ: C:\Users\YourName\AppData\Local\Google\Chrome\User Data\Default\History"
            className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm font-mono placeholder:text-[var(--color-ink-muted)]/50"
          />
          <p className="text-[10px] text-[var(--color-ink-muted)]">
            💡 Để trống nếu muốn dùng đường dẫn mặc định theo hệ điều hành.
          </p>
        </div>
      )}

      <button
        onClick={handleSync}
        disabled={pending}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
      >
        {pending ? "Đang trích xuất..." : "Trích xuất Chrome History"}
      </button>

      {result && (
        <p className={`mt-3 text-sm font-medium ${result.ok ? "text-green-500" : "text-[var(--color-danger)]"}`}>
          {result.message}
        </p>
      )}
    </section>
  );
}

/**
 * Xoá toàn bộ lịch sử đã lưu của một profile trên Postgres (chỉ render ở chế độ api).
 *
 * Vì sao có confirm: DELETE không hoàn tác được và lịch sử là dữ liệu cá nhân. Mutation
 * đi qua Server Action nên API key không xuống browser.
 */
export function ChromeHistoryDeleteForm({ defaultProfile }: { defaultProfile: string }) {
  const [profile, setProfile] = useState(defaultProfile);
  const [secret, setSecret] = useState("");
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  const handleDelete = () => {
    const name = profile.trim();
    if (!name || !secret) return;
    if (!window.confirm(`Xoá TOÀN BỘ lịch sử của profile "${name}" trong Postgres? Không thể hoàn tác.`)) return;
    const sent = secret;
    // Xoá mật khẩu khỏi state ngay sau khi lấy ra, dù thành công hay lỗi.
    setSecret("");
    setResult(null);
    startTransition(async () => {
      const res = await deleteChromeHistoryAction(name, sent);
      setResult(
        res.ok
          ? { ok: true, message: `Đã xoá ${res.deleted ?? 0} dòng của profile ${name}.` }
          : { ok: false, message: `Lỗi: ${res.error}` },
      );
    });
  };

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3">
      <span className="text-sm font-medium">Xoá theo profile:</span>
      <input
        type="text"
        value={profile}
        onChange={(e) => setProfile(e.target.value)}
        placeholder="Default"
        maxLength={200}
        className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-sm"
      />
      <input
        type="password"
        value={secret}
        onChange={(e) => setSecret(e.target.value)}
        placeholder="Mật khẩu nhập dữ liệu"
        autoComplete="new-password"
        maxLength={256}
        className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-sm"
      />
      <button
        type="button"
        onClick={handleDelete}
        disabled={pending || !profile.trim() || !secret}
        className="rounded-md bg-[var(--color-danger)] px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
      >
        {pending ? "Đang xoá..." : "Xoá"}
      </button>
      {result && (
        <span className={`text-xs ${result.ok ? "text-green-500" : "text-[var(--color-danger)]"}`}>{result.message}</span>
      )}
    </div>
  );
}
