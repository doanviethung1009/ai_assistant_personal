"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getVaultBlobAction, saveVaultBlobAction } from "@/app/vault-actions";
import {
  createVault,
  encryptPayload,
  MIN_PASSWORD_LENGTH,
  regenerateRecovery,
  rewrapPassword,
  unlockBlob,
  unlockWithRecovery,
  WrongPasswordError,
  type VaultBlob,
  type VaultEntry,
  type VaultField,
  type VaultSession,
} from "@/lib/vault/crypto";
import {
  ForgotPasswordForm,
  RecoveryKeyScreen,
  RegenerateRecoveryForm,
} from "@/components/vault-recovery";

const IDLE_LOCK_MS = 5 * 60 * 1000;
const REVEAL_MS = 15 * 1000;
const CLIPBOARD_CLEAR_MS = 30 * 1000;
const MASK = "••••••••••";

const INPUT =
  "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm";
const BTN =
  "rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-ink-muted)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink)] disabled:opacity-40";
const BTN_PRIMARY =
  "rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40";

const SYSTEM_TYPES: Record<string, { label: string; fields: Omit<VaultField, "id">[] }> = {
  database: {
    label: "Database",
    fields: [
      { label: "Host", value: "", secret: false },
      { label: "Port", value: "", secret: false },
      { label: "Database", value: "", secret: false },
      { label: "Username", value: "", secret: false },
      { label: "Password", value: "", secret: true },
      { label: "Connection string", value: "", secret: true },
    ],
  },
  server: {
    label: "Server / SSH",
    fields: [
      { label: "Host", value: "", secret: false },
      { label: "Username", value: "", secret: false },
      { label: "Password", value: "", secret: true },
      { label: "Private key", value: "", secret: true },
    ],
  },
  api: {
    label: "API / Token",
    fields: [
      { label: "Base URL", value: "", secret: false },
      { label: "API key", value: "", secret: true },
    ],
  },
  cloud: {
    label: "Cloud / Console",
    fields: [
      { label: "URL", value: "", secret: false },
      { label: "Username", value: "", secret: false },
      { label: "Password", value: "", secret: true },
      { label: "Access key", value: "", secret: true },
    ],
  },
  account: {
    label: "Tài khoản web",
    fields: [
      { label: "URL", value: "", secret: false },
      { label: "Username", value: "", secret: false },
      { label: "Password", value: "", secret: true },
    ],
  },
  other: { label: "Khác", fields: [{ label: "Giá trị", value: "", secret: true }] },
};

function uid(): string {
  return crypto.randomUUID();
}

function templateFields(type: string): VaultField[] {
  return (SYSTEM_TYPES[type] ?? SYSTEM_TYPES.other!).fields.map((f) => ({
    ...f,
    id: uid(),
  }));
}

function blankEntry(): VaultEntry {
  const now = new Date().toISOString();
  return {
    id: uid(),
    name: "",
    system_type: "database",
    project: "",
    tags: [],
    fields: templateFields("database"),
    notes: "",
    created_at: now,
    updated_at: now,
  };
}

type Phase = "loading" | "setup" | "recovery" | "forgot" | "locked" | "unlocked";

export function VaultClient() {
  const [phase, setPhase] = useState<Phase>("loading");
  const [blob, setBlob] = useState<VaultBlob | null>(null);
  const [entries, setEntries] = useState<VaultEntry[]>([]);
  const sessionRef = useRef<VaultSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const failCount = useRef(0);

  // Mã khôi phục chỉ nằm trong state lúc đang hiện cho người dùng; xóa ngay khi xong
  const [recoveryKey, setRecoveryKey] = useState<string | null>(null);
  const [hasRecovery, setHasRecovery] = useState(true);

  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [editing, setEditing] = useState<VaultEntry | null>(null);
  const [changingPassword, setChangingPassword] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  /** Gắn session mới và cập nhật cờ "đã có mã khôi phục" cho banner cảnh báo. */
  function adopt(session: VaultSession) {
    sessionRef.current = session;
    setHasRecovery(session.wraps.recovery !== null);
  }

  // ── Nạp blob ban đầu ──────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    void getVaultBlobAction().then((result) => {
      if (cancelled) return;
      if (!result.ok) {
        setError(result.error ?? "Lỗi đọc két");
        setPhase("locked");
        return;
      }
      setBlob(result.blob);
      setPhase(result.blob ? "locked" : "setup");
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Khoá: xoá sạch plaintext và khoá khỏi bộ nhớ ───────────────────
  const lock = useCallback(() => {
    sessionRef.current = null;
    setEntries([]);
    setEditing(null);
    setChangingPassword(false);
    setRegenerating(false);
    setRecoveryKey(null);
    setError(null);
    setSearch("");
    setPhase("locked");
  }, []);

  // Tự khoá sau 5 phút không thao tác
  useEffect(() => {
    if (phase !== "unlocked") return;
    let timer = setTimeout(lock, IDLE_LOCK_MS);
    const reset = () => {
      clearTimeout(timer);
      timer = setTimeout(lock, IDLE_LOCK_MS);
    };
    const events = ["mousemove", "keydown", "click", "scroll"] as const;
    events.forEach((e) => window.addEventListener(e, reset));
    return () => {
      clearTimeout(timer);
      events.forEach((e) => window.removeEventListener(e, reset));
    };
  }, [phase, lock]);

  // ── Lưu ───────────────────────────────────────────────────────────
  const persist = useCallback(
    async (next: VaultEntry[], session: VaultSession): Promise<boolean> => {
      const encrypted = await encryptPayload(session, { entries: next });
      const result = await saveVaultBlobAction(
        encrypted,
        blob?.updated_at ?? null,
      );
      if (!result.ok) {
        setError(result.error ?? "Lưu thất bại");
        return false;
      }
      setBlob(encrypted);
      setEntries(next);
      setError(null);
      return true;
    },
    [blob],
  );

  // ── Đặt mật khẩu lần đầu ──────────────────────────────────────────
  async function handleSetup(password: string) {
    setBusy(true);
    setError(null);
    try {
      const { session, recoveryKey: key } = await createVault(password);
      adopt(session);
      if (await persist([], session)) {
        // Hiện mã khôi phục một lần trước khi cho vào két
        setRecoveryKey(key);
        setPhase("recovery");
      }
    } finally {
      setBusy(false);
    }
  }

  // ── Quên mật khẩu: mở bằng mã khôi phục, đặt mật khẩu mới ─────────────────
  async function handleRecover(key: string, newPassword: string) {
    if (!blob) return;
    setBusy(true);
    setError(null);
    try {
      const { session, payload } = await unlockWithRecovery(key, newPassword, blob);
      if (await persist(payload.entries, session)) {
        adopt(session);
        failCount.current = 0;
        setPhase("unlocked");
      }
    } catch (err) {
      setError(
        err instanceof WrongPasswordError
          ? "Mã khôi phục không đúng."
          : err instanceof Error
            ? err.message
            : "Không khôi phục được két.",
      );
    } finally {
      setBusy(false);
    }
  }

  // ── Sinh mã khôi phục mới (mã cũ mất hiệu lực) ────────────────────────────
  async function handleRegenerateRecovery(password: string) {
    if (!blob) return;
    setBusy(true);
    setError(null);
    // Cùng cơ chế làm chậm khi nhập sai liên tục như mở khoá
    if (failCount.current >= 3) {
      await new Promise((r) => setTimeout(r, Math.min(failCount.current, 10) * 1000));
    }
    try {
      // Luôn xác thực lại bằng mật khẩu, không dựa vào phiên đang mở
      const { session: verified, payload } = await unlockBlob(password, blob);
      const { session, recoveryKey: key } = await regenerateRecovery(verified);
      if (await persist(payload.entries, session)) {
        failCount.current = 0;
        adopt(session);
        setEntries(payload.entries);
        setRegenerating(false);
        setRecoveryKey(key);
        setPhase("recovery");
      }
    } catch (err) {
      failCount.current += 1;
      setError(
        err instanceof WrongPasswordError
          ? "Mật khẩu master không đúng."
          : "Không sinh được mã khôi phục.",
      );
    } finally {
      setBusy(false);
    }
  }

  // ── Mở khoá ───────────────────────────────────────────────────────
  async function handleUnlock(password: string) {
    if (!blob) return;
    setBusy(true);
    setError(null);
    // Làm chậm dần khi nhập sai liên tục: hạn chế đoán mật khẩu tự động ngay
    // tại UI. Chặn thật sự vẫn là chi phí PBKDF2, không phải đoạn này.
    if (failCount.current >= 3) {
      await new Promise((r) => setTimeout(r, Math.min(failCount.current, 10) * 1000));
    }
    try {
      const { session, payload } = await unlockBlob(password, blob);
      adopt(session);
      failCount.current = 0;
      setEntries(payload.entries);
      setPhase("unlocked");
    } catch (err) {
      failCount.current += 1;
      setError(
        err instanceof WrongPasswordError ? err.message : "Không mở khoá được két.",
      );
    } finally {
      setBusy(false);
    }
  }

  // ── Đổi mật khẩu: kiểm tra lại mật khẩu cũ, wrap lại DEK, giữ nguyên mã khôi phục ──
  async function handleChangePassword(oldPw: string, newPw: string) {
    if (!blob) return;
    setBusy(true);
    setError(null);
    try {
      const { session: verified, payload } = await unlockBlob(oldPw, blob);
      const session = await rewrapPassword(verified, newPw);
      if (await persist(payload.entries, session)) {
        adopt(session);
        setChangingPassword(false);
      }
    } catch (err) {
      setError(
        err instanceof WrongPasswordError
          ? "Mật khẩu hiện tại không đúng."
          : "Đổi mật khẩu thất bại.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveEntry(entry: VaultEntry) {
    const session = sessionRef.current;
    if (!session) return;
    setBusy(true);
    const stamped = { ...entry, updated_at: new Date().toISOString() };
    const exists = entries.some((e) => e.id === stamped.id);
    const next = exists
      ? entries.map((e) => (e.id === stamped.id ? stamped : e))
      : [stamped, ...entries];
    if (await persist(next, session)) setEditing(null);
    setBusy(false);
  }

  async function handleDeleteEntry(id: string) {
    const session = sessionRef.current;
    if (!session) return;
    setBusy(true);
    await persist(entries.filter((e) => e.id !== id), session);
    setBusy(false);
  }

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return entries.filter((entry) => {
      if (typeFilter && entry.system_type !== typeFilter) return false;
      if (!q) return true;
      // Chỉ tìm trên trường KHÔNG bí mật, để search không biến thành đường
      // đọc secret gián tiếp.
      const haystack = [
        entry.name,
        entry.project,
        entry.tags.join(" "),
        ...entry.fields.filter((f) => !f.secret).map((f) => `${f.label} ${f.value}`),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [entries, search, typeFilter]);

  // ── Render ────────────────────────────────────────────────────────
  if (phase === "loading") {
    return <p className="text-sm text-[var(--color-ink-muted)]">Đang tải két…</p>;
  }

  if (phase === "setup") {
    return <PasswordGate mode="setup" busy={busy} error={error} onSubmit={handleSetup} />;
  }

  if (phase === "recovery" && recoveryKey) {
    return (
      <RecoveryKeyScreen
        recoveryKey={recoveryKey}
        onDone={() => {
          // Xoá mã khỏi RAM ngay khi người dùng xác nhận đã cất
          setRecoveryKey(null);
          setPhase("unlocked");
        }}
      />
    );
  }

  if (phase === "forgot") {
    return (
      <ForgotPasswordForm
        busy={busy}
        error={error}
        onSubmit={handleRecover}
        onCancel={() => {
          setError(null);
          setPhase("locked");
        }}
      />
    );
  }

  if (phase === "locked") {
    return (
      <PasswordGate
        mode="unlock"
        busy={busy}
        error={error}
        onSubmit={handleUnlock}
        onRegenerate={handleRegenerateRecovery}
        onForgot={() => {
          setError(null);
          setPhase("forgot");
        }}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <input
          id="vault-search"
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Tìm theo tên, dự án, tag, host…"
          className={`${INPUT} max-w-xs`}
          aria-label="Tìm trong két"
        />
        <select
          id="vault-type-filter"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className={`${INPUT} max-w-[180px]`}
          aria-label="Lọc theo loại hệ thống"
        >
          <option value="">Mọi loại</option>
          {Object.entries(SYSTEM_TYPES).map(([value, { label }]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <div className="ml-auto flex flex-wrap gap-2">
          <button
            id="vault-add"
            type="button"
            className={BTN_PRIMARY}
            onClick={() => setEditing(blankEntry())}
          >
            + Thêm mục
          </button>
          <button
            id="vault-change-password"
            type="button"
            className={BTN}
            onClick={() => setChangingPassword(true)}
          >
            Đổi mật khẩu
          </button>
          <button
            id="vault-regenerate-recovery"
            type="button"
            className={BTN}
            disabled={busy}
            onClick={() => {
              setError(null);
              setRegenerating(true);
            }}
          >
            {hasRecovery ? "Sinh lại mã khôi phục" : "Tạo mã khôi phục"}
          </button>
          <a className={BTN} href="/api/export?format=json&entity=vault">
            Sao lưu (đã mã hoá)
          </a>
          <button id="vault-lock" type="button" className={BTN} onClick={lock}>
            🔒 Khoá ngay
          </button>
        </div>
      </div>

      {error ? (
        <p role="alert" className="text-xs text-[var(--color-danger)]">
          {error}
        </p>
      ) : null}

      {!hasRecovery ? (
        <div
          role="status"
          className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs"
        >
          <span>
            Két này <strong>chưa có mã khôi phục</strong>. Quên mật khẩu là mất toàn
            bộ dữ liệu.
          </span>
          <button
            type="button"
            className={BTN}
            disabled={busy}
            onClick={() => {
              setError(null);
              setRegenerating(true);
            }}
          >
            Tạo mã khôi phục ngay
          </button>
        </div>
      ) : null}

      {regenerating ? (
        <RegenerateRecoveryForm
          busy={busy}
          hasRecovery={hasRecovery}
          error={null}
          onSubmit={(pw) => void handleRegenerateRecovery(pw)}
          onCancel={() => setRegenerating(false)}
        />
      ) : null}

      {changingPassword ? (
        <ChangePasswordForm
          busy={busy}
          onCancel={() => setChangingPassword(false)}
          onSubmit={handleChangePassword}
        />
      ) : null}

      {editing ? (
        <EntryForm
          key={editing.id}
          initial={editing}
          busy={busy}
          onCancel={() => setEditing(null)}
          onSave={handleSaveEntry}
        />
      ) : null}

      {visible.length === 0 ? (
        <p className="rounded-lg border border-dashed border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-ink-muted)]">
          {entries.length === 0
            ? "Két trống. Bấm “Thêm mục” để lưu thông tin hệ thống đầu tiên."
            : "Không có mục nào khớp bộ lọc."}
        </p>
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {visible.map((entry) => (
            <EntryCard
              key={entry.id}
              entry={entry}
              onEdit={() => setEditing(entry)}
              onDelete={() => void handleDeleteEntry(entry.id)}
            />
          ))}
        </ul>
      )}

      <p className="text-xs text-[var(--color-ink-muted)]">
        Tự khoá sau 5 phút không thao tác. Giá trị bí mật được che mặc định và
        tự che lại sau 15 giây.
      </p>
    </div>
  );
}

// ── Cổng mật khẩu ────────────────────────────────────────────────────────

function PasswordGate({
  mode,
  busy,
  error,
  onSubmit,
  onForgot,
  onRegenerate,
}: {
  mode: "setup" | "unlock";
  busy: boolean;
  error: string | null;
  onSubmit: (password: string) => void;
  onForgot?: () => void;
  /** Nhập mật khẩu rồi mở khoá kèm sinh lại mã khôi phục. */
  onRegenerate?: (password: string) => void;
}) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const isSetup = mode === "setup";

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (isSetup) {
      if (password.length < MIN_PASSWORD_LENGTH) {
        setLocalError(`Mật khẩu tối thiểu ${MIN_PASSWORD_LENGTH} ký tự.`);
        return;
      }
      if (password !== confirm) {
        setLocalError("Hai lần nhập mật khẩu không khớp.");
        return;
      }
    }
    setLocalError(null);
    onSubmit(password);
  }

  return (
    <form
      onSubmit={submit}
      className="mx-auto flex w-full max-w-md flex-col gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-6"
    >
      <div className="text-3xl" aria-hidden>
        {isSetup ? "🛡️" : "🔒"}
      </div>
      <h2 className="text-lg font-semibold">
        {isSetup ? "Tạo mật khẩu master cho Két" : "Két đang khoá"}
      </h2>
      <p className="text-xs text-[var(--color-ink-muted)]">
        {isSetup
          ? "Dữ liệu được mã hoá ngay trên trình duyệt (AES-256). Server chỉ lưu bản mã. "
          : "Nhập mật khẩu master để xem các mục đã lưu."}
        {isSetup ? (
          <strong className="text-[var(--color-danger)]">
            Sau bước này bạn sẽ nhận một mã khôi phục, hãy cất kỹ. Mất cả mật
            khẩu lẫn mã khôi phục thì không lấy lại được dữ liệu.
          </strong>
        ) : null}
      </p>
      <input
        id="vault-password"
        type="password"
        autoFocus
        autoComplete={isSetup ? "new-password" : "current-password"}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Mật khẩu master"
        className={INPUT}
        aria-label="Mật khẩu master"
      />
      {isSetup ? (
        <input
          id="vault-password-confirm"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder="Nhập lại mật khẩu"
          className={INPUT}
          aria-label="Nhập lại mật khẩu master"
        />
      ) : null}
      {localError || error ? (
        <p role="alert" className="text-xs text-[var(--color-danger)]">
          {localError ?? error}
        </p>
      ) : null}
      <button type="submit" disabled={busy || !password} className={BTN_PRIMARY}>
        {busy ? "Đang xử lý…" : isSetup ? "Tạo két" : "Mở khoá"}
      </button>
      {!isSetup && onRegenerate ? (
        <button
          id="vault-unlock-regenerate"
          type="button"
          disabled={busy || !password}
          onClick={() => onRegenerate(password)}
          className={BTN}
        >
          Mở khoá và sinh lại mã khôi phục
        </button>
      ) : null}
      {!isSetup && onForgot ? (
        <button
          id="vault-forgot"
          type="button"
          onClick={onForgot}
          className="text-xs text-[var(--color-ink-muted)] underline hover:text-[var(--color-ink)]"
        >
          Quên mật khẩu? Dùng mã khôi phục
        </button>
      ) : null}
    </form>
  );
}

function ChangePasswordForm({
  busy,
  onCancel,
  onSubmit,
}: {
  busy: boolean;
  onCancel: () => void;
  onSubmit: (oldPw: string, newPw: string) => void;
}) {
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (newPw.length < MIN_PASSWORD_LENGTH) {
      setLocalError(`Mật khẩu mới tối thiểu ${MIN_PASSWORD_LENGTH} ký tự.`);
      return;
    }
    if (newPw !== confirm) {
      setLocalError("Hai lần nhập mật khẩu mới không khớp.");
      return;
    }
    setLocalError(null);
    onSubmit(oldPw, newPw);
  }

  return (
    <form
      onSubmit={submit}
      className="grid gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4 sm:grid-cols-3"
    >
      <input type="password" autoComplete="current-password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} placeholder="Mật khẩu hiện tại" className={INPUT} aria-label="Mật khẩu hiện tại" />
      <input type="password" autoComplete="new-password" value={newPw} onChange={(e) => setNewPw(e.target.value)} placeholder="Mật khẩu mới" className={INPUT} aria-label="Mật khẩu mới" />
      <input type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="Nhập lại mật khẩu mới" className={INPUT} aria-label="Nhập lại mật khẩu mới" />
      {localError ? (
        <p role="alert" className="text-xs text-[var(--color-danger)] sm:col-span-3">
          {localError}
        </p>
      ) : null}
      <div className="flex gap-2 sm:col-span-3">
        <button type="submit" disabled={busy || !oldPw || !newPw} className={BTN_PRIMARY}>
          {busy ? "Đang mã hoá lại…" : "Đổi mật khẩu"}
        </button>
        <button type="button" className={BTN} onClick={onCancel}>
          Huỷ
        </button>
      </div>
    </form>
  );
}

// ── Thẻ mục + trường che/hiện ─────────────────────────────────────────

function EntryCard({
  entry,
  onEdit,
  onDelete,
}: {
  entry: VaultEntry;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const typeLabel = SYSTEM_TYPES[entry.system_type]?.label ?? entry.system_type;

  return (
    <li className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold">{entry.name}</h3>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <span className="inline-flex items-center rounded-full bg-teal-500/15 px-2 py-0.5 text-xs font-medium text-teal-300 ring-1 ring-inset ring-teal-500/30">
              {typeLabel}
            </span>
            {entry.project ? (
              <span className="inline-flex items-center rounded-full bg-white/5 px-2 py-0.5 text-xs ring-1 ring-inset ring-white/10">
                {entry.project}
              </span>
            ) : null}
            {entry.tags.map((tag) => (
              <span key={tag} className="rounded bg-slate-500/15 px-2 py-0.5 text-xs text-slate-300">
                #{tag}
              </span>
            ))}
          </div>
        </div>
        <div className="flex shrink-0 gap-1">
          <button type="button" className={BTN} onClick={onEdit}>
            Sửa
          </button>
          {confirmingDelete ? (
            <>
              <button
                type="button"
                className="rounded-md border border-[var(--color-danger)] px-3 py-1.5 text-xs text-[var(--color-danger)]"
                onClick={onDelete}
              >
                Xoá thật
              </button>
              <button type="button" className={BTN} onClick={() => setConfirmingDelete(false)}>
                Huỷ
              </button>
            </>
          ) : (
            <button type="button" className={BTN} onClick={() => setConfirmingDelete(true)}>
              Xoá
            </button>
          )}
        </div>
      </div>

      <dl className="mt-3 flex flex-col gap-1.5">
        {entry.fields.map((field) => (
          <FieldRow key={field.id} field={field} />
        ))}
      </dl>

      {entry.notes ? (
        <p className="mt-3 whitespace-pre-wrap text-xs text-[var(--color-ink-muted)]">
          {entry.notes}
        </p>
      ) : null}
    </li>
  );
}

function FieldRow({ field }: { field: VaultField }) {
  const [revealed, setRevealed] = useState(false);
  const [copied, setCopied] = useState(false);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Dọn timer khi unmount (ví dụ vừa bấm Khoá), tránh setState sau khi huỷ
  useEffect(
    () => () => {
      if (hideTimer.current) clearTimeout(hideTimer.current);
    },
    [],
  );

  function toggle() {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    if (revealed) {
      setRevealed(false);
      return;
    }
    setRevealed(true);
    hideTimer.current = setTimeout(() => setRevealed(false), REVEAL_MS);
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(field.value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
      if (field.secret) {
        // Best-effort: chỉ xoá nếu clipboard vẫn còn đúng giá trị mình đã chép
        setTimeout(async () => {
          try {
            if ((await navigator.clipboard.readText()) === field.value) {
              await navigator.clipboard.writeText("");
            }
          } catch {
            // Trình duyệt không cho đọc clipboard: bỏ qua
          }
        }, CLIPBOARD_CLEAR_MS);
      }
    } catch {
      // clipboard bị chặn (http, không có quyền): không làm gì
    }
  }

  const shown = !field.secret || revealed;

  return (
    <div className="flex items-center gap-2 text-xs">
      <dt className="w-32 shrink-0 truncate text-[var(--color-ink-muted)]">{field.label}</dt>
      <dd
        className={`min-w-0 flex-1 truncate rounded bg-[var(--color-surface)] px-2 py-1 font-mono ${
          shown ? "" : "select-none tracking-widest text-[var(--color-ink-muted)]"
        }`}
      >
        {/* Độ dài mask cố định, không lộ độ dài thật của secret */}
        {field.value === "" ? "—" : shown ? field.value : MASK}
      </dd>
      {field.secret && field.value !== "" ? (
        <button type="button" className={BTN} onClick={toggle} aria-pressed={revealed}>
          {revealed ? "Ẩn" : "Hiện"}
        </button>
      ) : null}
      {field.value !== "" ? (
        <button type="button" className={BTN} onClick={() => void copy()}>
          {copied ? "Đã chép" : "Chép"}
        </button>
      ) : null}
    </div>
  );
}

// ── Form thêm / sửa ──────────────────────────────────────────────────

function EntryForm({
  initial,
  busy,
  onCancel,
  onSave,
}: {
  initial: VaultEntry;
  busy: boolean;
  onCancel: () => void;
  onSave: (entry: VaultEntry) => void;
}) {
  const [entry, setEntry] = useState<VaultEntry>(initial);
  const [tagText, setTagText] = useState(initial.tags.join(", "));
  const isNew = initial.name === "";

  function setField(id: string, patch: Partial<VaultField>) {
    setEntry((prev) => ({
      ...prev,
      fields: prev.fields.map((f) => (f.id === id ? { ...f, ...patch } : f)),
    }));
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!entry.name.trim()) return;
    onSave({
      ...entry,
      name: entry.name.trim(),
      tags: tagText
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      // Bỏ dòng trống hoàn toàn (không có nhãn lẫn giá trị)
      fields: entry.fields.filter((f) => f.label.trim() || f.value),
    });
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-3 rounded-lg border border-[var(--color-accent)]/40 bg-[var(--color-surface-raised)] p-4"
    >
      <h2 className="text-sm font-semibold">{isNew ? "Thêm mục mới" : "Sửa mục"}</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <input
          id="vault-entry-name"
          required
          value={entry.name}
          onChange={(e) => setEntry({ ...entry, name: e.target.value })}
          placeholder="Tên (vd: Postgres prod)"
          className={INPUT}
          aria-label="Tên mục"
        />
        <select
          value={entry.system_type}
          onChange={(e) => {
            const type = e.target.value;
            setEntry((prev) => ({
              ...prev,
              system_type: type,
              // Chỉ áp template khi chưa nhập gì, tránh mất dữ liệu đang gõ
              fields: prev.fields.every((f) => !f.value)
                ? templateFields(type)
                : prev.fields,
            }));
          }}
          className={INPUT}
          aria-label="Loại hệ thống"
        >
          {Object.entries(SYSTEM_TYPES).map(([value, { label }]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <input
          value={entry.project}
          onChange={(e) => setEntry({ ...entry, project: e.target.value })}
          placeholder="Dự án (tuỳ chọn)"
          className={INPUT}
          aria-label="Dự án"
        />
      </div>

      <div className="flex flex-col gap-2">
        {entry.fields.map((field) => (
          <div key={field.id} className="grid grid-cols-[1fr_2fr_auto_auto] items-center gap-2">
            <input
              value={field.label}
              onChange={(e) => setField(field.id, { label: e.target.value })}
              placeholder="Nhãn"
              className={INPUT}
              aria-label="Nhãn trường"
            />
            <input
              value={field.value}
              onChange={(e) => setField(field.id, { value: e.target.value })}
              type={field.secret ? "password" : "text"}
              autoComplete="off"
              placeholder="Giá trị"
              className={`${INPUT} font-mono`}
              aria-label={`Giá trị ${field.label}`}
            />
            <label className="flex items-center gap-1 text-xs text-[var(--color-ink-muted)]">
              <input
                type="checkbox"
                checked={field.secret}
                onChange={(e) => setField(field.id, { secret: e.target.checked })}
              />
              Bí mật
            </label>
            <button
              type="button"
              className={BTN}
              onClick={() =>
                setEntry((prev) => ({
                  ...prev,
                  fields: prev.fields.filter((f) => f.id !== field.id),
                }))
              }
              aria-label={`Xoá trường ${field.label}`}
            >
              ✕
            </button>
          </div>
        ))}
        <button
          type="button"
          className={`${BTN} self-start`}
          onClick={() =>
            setEntry((prev) => ({
              ...prev,
              fields: [...prev.fields, { id: uid(), label: "", value: "", secret: false }],
            }))
          }
        >
          + Thêm trường
        </button>
      </div>

      <input
        value={tagText}
        onChange={(e) => setTagText(e.target.value)}
        placeholder="Tag, cách nhau bằng dấu phẩy"
        className={INPUT}
        aria-label="Tag"
      />
      <textarea
        value={entry.notes}
        onChange={(e) => setEntry({ ...entry, notes: e.target.value })}
        placeholder="Ghi chú: luồng kết nối, người phụ trách, ngày hết hạn…"
        className={`${INPUT} min-h-[80px]`}
        aria-label="Ghi chú"
      />

      <div className="flex gap-2">
        <button type="submit" disabled={busy || !entry.name.trim()} className={BTN_PRIMARY}>
          {busy ? "Đang mã hoá…" : "Lưu"}
        </button>
        <button type="button" className={BTN} onClick={onCancel}>
          Huỷ
        </button>
      </div>
    </form>
  );
}
