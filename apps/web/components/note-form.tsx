"use client";

import { useMemo, useRef, useState, useTransition } from "react";

import { createNoteAction } from "@/app/actions";
import { detectDanger, detectSecretHint } from "@/lib/note-danger";
import { NOTE_KINDS, NOTE_KIND_LABELS, type NoteKind } from "@/lib/types";

const INPUT_CLASS =
  "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm";
const LABEL_CLASS =
  "mb-1 block text-xs font-medium text-[var(--color-ink-muted)]";

/** Ô nhập nội dung dùng font đơn cách, vì hầu hết là câu lệnh và SQL. */
const CONTENT_CLASS = `${INPUT_CLASS} min-h-[140px] font-mono text-xs leading-relaxed`;

export function NoteForm({
  projects,
}: {
  projects: { id: string; key: string; name: string }[];
}) {
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const formRef = useRef<HTMLFormElement>(null);

  // Nội dung giữ ở state để chạy heuristic ngay khi gõ. Các field khác để
  // form tự quản lý, không cần controlled.
  const [content, setContent] = useState("");
  const [kind, setKind] = useState<NoteKind>("command");

  // Người dùng đã tự bật hay tắt ô "cẩn thận" chưa. Trước khi họ chạm vào,
  // ô này đi theo heuristic; sau đó thì tôn trọng lựa chọn của họ và không
  // tự đổi nữa, kể cả khi họ sửa tiếp nội dung.
  const [dangerTouched, setDangerTouched] = useState(false);
  const [dangerChecked, setDangerChecked] = useState(false);

  const dangerSignals = useMemo(() => detectDanger(content), [content]);
  const secretSignals = useMemo(() => detectSecretHint(content), [content]);

  const isDangerous = dangerTouched ? dangerChecked : dangerSignals.length > 0;

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const form = new FormData(event.currentTarget);
    const tags = String(form.get("tags") ?? "")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);

    startTransition(async () => {
      const result = await createNoteAction({
        title: String(form.get("title") ?? ""),
        content: String(form.get("content") ?? ""),
        kind,
        description: String(form.get("description") ?? ""),
        context: String(form.get("context") ?? ""),
        projectId: String(form.get("project_id") ?? ""),
        tags,
        isPinned: form.get("is_pinned") === "on",
        isDangerous,
      });

      if (result.ok) {
        formRef.current?.reset();
        setContent("");
        setKind("command");
        setDangerTouched(false);
        setDangerChecked(false);
      } else {
        setError(result.error ?? "Lưu note thất bại");
      }
    });
  }

  return (
    <details className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)]">
      <summary className="cursor-pointer px-4 py-3 text-sm font-medium">
        Thêm vào sổ tay
      </summary>

      <form
        ref={formRef}
        onSubmit={handleSubmit}
        className="flex flex-col gap-3 border-t border-[var(--color-border)] p-4"
        aria-label="Thêm note"
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_160px]">
          <div>
            <label htmlFor="note-title" className={LABEL_CLASS}>
              Tiêu đề
            </label>
            <input
              id="note-title"
              name="title"
              type="text"
              required
              maxLength={300}
              placeholder="Backup database ra file gzip"
              className={INPUT_CLASS}
            />
          </div>

          <div>
            <label htmlFor="note-kind" className={LABEL_CLASS}>
              Loại
            </label>
            <select
              id="note-kind"
              name="kind"
              value={kind}
              onChange={(event) => setKind(event.target.value as NoteKind)}
              className={INPUT_CLASS}
            >
              {NOTE_KINDS.map((value) => (
                <option key={value} value={value}>
                  {NOTE_KIND_LABELS[value]}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label htmlFor="note-content" className={LABEL_CLASS}>
            Nội dung để copy
          </label>
          <textarea
            id="note-content"
            name="content"
            required
            maxLength={20_000}
            value={content}
            onChange={(event) => setContent(event.target.value)}
            spellCheck={false}
            placeholder={"docker compose exec -T postgres pg_dump -U builder -d builder_ai | gzip > backup.sql.gz"}
            className={CONTENT_CLASS}
          />
          <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
            Nội dung được lưu nguyên văn và chỉ dùng để copy. App không bao giờ
            tự chạy nó.
          </p>
        </div>

        {secretSignals.length > 0 ? (
          <div
            role="alert"
            className="rounded-md border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10 px-3 py-2 text-xs"
          >
            <p className="font-medium">Có thể đang chứa bí mật</p>
            <ul className="mt-1 list-disc pl-4 text-[var(--color-ink-muted)]">
              {secretSignals.map((signal) => (
                <li key={signal.reason}>{signal.reason}</li>
              ))}
            </ul>
            <p className="mt-1 text-[var(--color-ink-muted)]">
              Sổ tay lưu văn bản thuần, không mã hoá. Nên thay giá trị thật
              bằng tên biến, ví dụ <code>$POSTGRES_PASSWORD</code>.
            </p>
          </div>
        ) : null}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="note-context" className={LABEL_CLASS}>
              Nơi áp dụng
            </label>
            <input
              id="note-context"
              name="context"
              type="text"
              maxLength={200}
              placeholder="máy prod, DB builder_ai"
              className={INPUT_CLASS}
            />
          </div>

          <div>
            <label htmlFor="note-project" className={LABEL_CLASS}>
              Dự án
            </label>
            <select id="note-project" name="project_id" className={INPUT_CLASS}>
              <option value="">Không thuộc dự án nào</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.key} — {project.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label htmlFor="note-description" className={LABEL_CLASS}>
            Vì sao cần, khi nào dùng
          </label>
          <textarea
            id="note-description"
            name="description"
            rows={2}
            placeholder="Chạy trước mỗi lần migrate trên prod."
            className={INPUT_CLASS}
          />
        </div>

        <div>
          <label htmlFor="note-tags" className={LABEL_CLASS}>
            Tag, cách nhau bằng dấu phẩy
          </label>
          <input
            id="note-tags"
            name="tags"
            type="text"
            placeholder="postgres, backup"
            className={INPUT_CLASS}
          />
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" name="is_pinned" className="size-4" />
            Ghim lên đầu
          </label>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="is_dangerous"
              checked={isDangerous}
              onChange={(event) => {
                setDangerTouched(true);
                setDangerChecked(event.target.checked);
              }}
              className="size-4"
            />
            Đánh dấu cẩn thận
          </label>

          <button
            type="submit"
            disabled={pending}
            className="ml-auto rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {pending ? "Đang lưu…" : "Lưu"}
          </button>
        </div>

        {dangerSignals.length > 0 ? (
          <div className="rounded-md border border-[var(--color-border)] px-3 py-2 text-xs text-[var(--color-ink-muted)]">
            <p>
              Đã tự tích &ldquo;cẩn thận&rdquo; vì phát hiện:{" "}
              {dangerSignals.map((signal) => signal.reason).join("; ")}. Bỏ tích
              nếu bạn thấy không cần.
            </p>
          </div>
        ) : null}

        {error ? (
          <p role="alert" className="text-sm text-[var(--color-danger)]">
            {error}
          </p>
        ) : null}
      </form>
    </details>
  );
}
