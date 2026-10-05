"use client";

import { useState } from "react";

import { MIN_PASSWORD_LENGTH } from "@/lib/vault/crypto";

const INPUT =
  "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm";
const BTN =
  "rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-ink-muted)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink)] disabled:opacity-40";
const BTN_PRIMARY =
  "rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40";

/**
 * Hiện mã khôi phục ĐÚNG MỘT LẦN. Mã chỉ tồn tại trong RAM của trình duyệt
 * và trên giấy/password manager của người dùng; server không giữ bản gốc,
 * nên đóng màn hình này là không xem lại được nữa (chỉ tạo mã mới).
 */
export function RecoveryKeyScreen({
  recoveryKey,
  onDone,
}: {
  recoveryKey: string;
  onDone: () => void;
}) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(recoveryKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard bị chặn: người dùng vẫn chép tay hoặc tải file được
    }
  }

  function download() {
    const text =
      `Mã khôi phục Két - Builder AI Assistant\n\n${recoveryKey}\n\n` +
      "Cất nơi an toàn, KHÔNG để cùng chỗ với mật khẩu master.\n" +
      "Ai có mã này đều mở được két của bạn.\n";
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "vault-recovery-key.txt";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col gap-3 rounded-xl border border-amber-500/40 bg-[var(--color-surface-raised)] p-6">
      <div className="text-3xl" aria-hidden>
        🗝️
      </div>
      <h2 className="text-lg font-semibold">Lưu mã khôi phục của bạn</h2>
      <p className="text-xs text-[var(--color-ink-muted)]">
        Nếu quên mật khẩu master, đây là cách DUY NHẤT mở lại két. Mã chỉ hiện
        một lần. Hãy in ra giấy hoặc lưu vào password manager, và{" "}
        <strong className="text-[var(--color-danger)]">
          đừng để cùng chỗ với mật khẩu master
        </strong>
        . Ai có mã này đều mở được két.
      </p>
      <p
        id="vault-recovery-key"
        className="select-all break-all rounded-md bg-[var(--color-surface)] px-3 py-3 text-center font-mono text-base tracking-wider"
      >
        {recoveryKey}
      </p>
      <div className="flex gap-2">
        <button type="button" className={BTN} onClick={() => void copy()}>
          {copied ? "Đã chép" : "Chép mã"}
        </button>
        <button type="button" className={BTN} onClick={download}>
          Tải file .txt
        </button>
        <button type="button" className={BTN} onClick={() => window.print()}>
          In
        </button>
      </div>
      <label className="flex items-start gap-2 text-xs">
        <input
          type="checkbox"
          checked={saved}
          onChange={(e) => setSaved(e.target.checked)}
          className="mt-0.5"
        />
        Tôi đã cất mã khôi phục ở nơi an toàn và hiểu rằng sẽ không xem lại được.
      </label>
      <button
        id="vault-recovery-done"
        type="button"
        disabled={!saved}
        onClick={onDone}
        className={BTN_PRIMARY}
      >
        Tiếp tục vào két
      </button>
    </div>
  );
}

/** Quên mật khẩu: nhập mã khôi phục + đặt mật khẩu mới. */
export function ForgotPasswordForm({
  busy,
  error,
  onSubmit,
  onCancel,
}: {
  busy: boolean;
  error: string | null;
  onSubmit: (recoveryKey: string, newPassword: string) => void;
  onCancel: () => void;
}) {
  const [key, setKey] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (password.length < MIN_PASSWORD_LENGTH) {
      setLocalError(`Mật khẩu mới tối thiểu ${MIN_PASSWORD_LENGTH} ký tự.`);
      return;
    }
    if (password !== confirm) {
      setLocalError("Hai lần nhập mật khẩu mới không khớp.");
      return;
    }
    setLocalError(null);
    onSubmit(key, password);
  }

  return (
    <form
      onSubmit={submit}
      className="mx-auto flex w-full max-w-md flex-col gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-6"
    >
      <div className="text-3xl" aria-hidden>
        🗝️
      </div>
      <h2 className="text-lg font-semibold">Khôi phục bằng mã</h2>
      <p className="text-xs text-[var(--color-ink-muted)]">
        Nhập mã khôi phục đã lưu khi tạo két và đặt mật khẩu master mới. Dữ
        liệu trong két được giữ nguyên.
      </p>
      <input
        id="vault-forgot-key"
        autoFocus
        autoComplete="off"
        spellCheck={false}
        value={key}
        onChange={(e) => setKey(e.target.value)}
        placeholder="XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX"
        className={`${INPUT} font-mono uppercase`}
        aria-label="Mã khôi phục"
      />
      <input
        type="password"
        autoComplete="new-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Mật khẩu master mới"
        className={INPUT}
        aria-label="Mật khẩu master mới"
      />
      <input
        type="password"
        autoComplete="new-password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        placeholder="Nhập lại mật khẩu mới"
        className={INPUT}
        aria-label="Nhập lại mật khẩu master mới"
      />
      {localError || error ? (
        <p role="alert" className="text-xs text-[var(--color-danger)]">
          {localError ?? error}
        </p>
      ) : null}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy || !key.trim() || !password}
          className={BTN_PRIMARY}
        >
          {busy ? "Đang khôi phục…" : "Khôi phục và đặt mật khẩu mới"}
        </button>
        <button type="button" className={BTN} onClick={onCancel}>
          Quay lại
        </button>
      </div>
    </form>
  );
}

/**
 * Sinh lại mã khôi phục: bắt buộc nhập lại mật khẩu master, kể cả khi két
 * đang mở. Phiên đang mở có thể do người khác ngồi vào máy lúc bạn rời đi;
 * mã khôi phục là chìa khoá dự phòng nên không được đổi chỉ bằng một cú bấm.
 */
export function RegenerateRecoveryForm({
  busy,
  hasRecovery,
  error,
  onSubmit,
  onCancel,
}: {
  busy: boolean;
  hasRecovery: boolean;
  error: string | null;
  onSubmit: (password: string) => void;
  onCancel: () => void;
}) {
  const [password, setPassword] = useState("");

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(password);
      }}
      className="flex flex-col gap-2 rounded-lg border border-amber-500/40 bg-[var(--color-surface-raised)] p-4"
    >
      <h2 className="text-sm font-semibold">
        {hasRecovery ? "Sinh lại mã khôi phục" : "Tạo mã khôi phục"}
      </h2>
      <p className="text-xs text-[var(--color-ink-muted)]">
        {hasRecovery ? (
          <>
            Mã khôi phục hiện tại sẽ <strong>mất hiệu lực ngay</strong>. Nhập
            mật khẩu master để xác nhận.
          </>
        ) : (
          "Nhập mật khẩu master để xác nhận và tạo mã khôi phục đầu tiên."
        )}
      </p>
      <div className="flex flex-wrap gap-2">
        <input
          id="vault-regenerate-password"
          type="password"
          autoFocus
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Mật khẩu master"
          className={`${INPUT} max-w-xs`}
          aria-label="Mật khẩu master để xác nhận"
        />
        <button type="submit" disabled={busy || !password} className={BTN_PRIMARY}>
          {busy ? "Đang xử lý…" : "Xác nhận và sinh mã"}
        </button>
        <button type="button" className={BTN} onClick={onCancel}>
          Huỷ
        </button>
      </div>
      {error ? (
        <p role="alert" className="text-xs text-[var(--color-danger)]">
          {error}
        </p>
      ) : null}
    </form>
  );
}
