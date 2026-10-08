"use client";

import { useState, useTransition } from "react";

import { importToCoreAction } from "@/app/actions";
import { importChromeHistoryToCoreAction } from "@/app/actions-chrome";
import type {
  BrowserHistoryImportReport,
  EntityCounts,
  ImportIssue,
  ImportReport,
  Replacement,
} from "@/lib/types";

const MAX_BYTES = 8 * 1024 * 1024;
const MAX_ISSUES_SHOWN = 50;

type Kind = "datafile" | "ai-logs" | "chrome-history";

const KIND_OPTIONS: { value: Kind; label: string }[] = [
  { value: "datafile", label: "JSON Project/Task/Note (builder-data.json)" },
  { value: "ai-logs", label: "JSON Nhật ký AI (ai-logs.json)" },
  { value: "chrome-history", label: "JSON Lịch sử Chrome (chrome-history.json)" },
];

const ENTITY_LABELS: Record<string, string> = {
  projects: "Project",
  tasks: "Task",
  task_events: "Nhật ký task",
  notes: "Sổ tay",
  ai_logs: "Nhật ký AI",
  // Cài đặt (current_users, sync_urls): counts dùng khoá `settings`, replacement/issue dùng `setting`.
  settings: "Cài đặt",
  setting: "Cài đặt",
  project: "Project",
  task: "Task",
  note: "Sổ tay",
  ai_log: "Nhật ký AI",
};

const INPUT_CLASS =
  "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm";
const LABEL_CLASS = "mb-1 block text-xs font-medium text-[var(--color-ink-muted)]";

/** Định danh "cùng một file" cho việc đối chiếu lần Kiểm tra với lần Nhập thật. */
function fileKey(file: File, kind: Kind): string {
  return `${kind}|${file.name}|${file.size}|${file.lastModified}`;
}

function sum(report: ImportReport, field: "replaced" | "replaced_older"): number {
  return Object.values(report.counts).reduce((total, c: EntityCounts) => total + c[field], 0);
}

/** Hiển thị giá trị bất kỳ thành chuỗi ngắn, luôn là text (không HTML). */
function show(value: unknown): string {
  if (value === null || value === undefined) return "(trống)";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > 200 ? `${text.slice(0, 200)}…` : text === "" ? "(chuỗi rỗng)" : text;
}

/**
 * Nhập file backup JSON vào Postgres, chỉ dùng ở chế độ DATA_SOURCE=api.
 *
 * ══════════════════════════════════════════════════════════════════════
 *  NHẬP THẬT GHI ĐÈ BẢN GHI ĐÃ CÓ trong Postgres bằng nội dung file, và
 *  file cũ có thể đè lên trạng thái mới hơn. Vì vậy luồng bắt buộc là:
 *  Kiểm tra (dry_run) → đọc báo cáo/diff → tích xác nhận → Nhập thật với
 *  `expect_replaced` đúng số đã Kiểm tra. Không có đường tắt bỏ qua Kiểm tra.
 * ══════════════════════════════════════════════════════════════════════
 *
 * Panel không gọi core trực tiếp: mọi thứ đi qua Server Action nên API key
 * không xuống browser. Nội dung từ báo cáo render bằng text node.
 */
export function CoreImportPanel() {
  const [kind, setKind] = useState<Kind>("datafile");
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<ImportReport | null>(null);
  // Khoá của file đã được Kiểm tra; Nhập thật chỉ mở khi khớp file đang chọn.
  const [checkedKey, setCheckedKey] = useState<string | null>(null);
  const [done, setDone] = useState<ImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ackReplace, setAckReplace] = useState(false);
  const [ackOlder, setAckOlder] = useState(false);
  // Mật khẩu IMPORT_COMMIT_SECRET gõ tay cho mỗi lần Nhập thật. Chỉ nằm trong state của
  // component: không lưu localStorage, không đưa vào URL, và bị xoá sau mỗi lần thử nhập.
  const [secret, setSecret] = useState("");
  // Mặc định TẮT: task đang `personal` trong Postgres không bị file ghi đè (S8). Phải gửi
  // cùng giá trị ở Kiểm tra lẫn Nhập thật, nên đổi ô này buộc Kiểm tra lại.
  const [includePersonal, setIncludePersonal] = useState(false);
  const [pending, startTransition] = useTransition();

  function resetResult() {
    setReport(null);
    setCheckedKey(null);
    setDone(null);
    setError(null);
    setAckReplace(false);
    setAckOlder(false);
    setSecret("");
  }

  function onFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const next = event.target.files?.[0] ?? null;
    resetResult();
    setIncludePersonal(false);
    if (next && next.size > MAX_BYTES) {
      setFile(null);
      event.target.value = "";
      setError("File vượt quá 8 MB. Chia nhỏ file hoặc nhập bằng cách khác.");
      return;
    }
    setFile(next);
  }

  function messageFor(status: number | undefined, fallback: string): string {
    if (status === 409) {
      return "Đang có một lần nhập khác chạy, hoặc dữ liệu đang bị khoá quá lâu. Đợi một chút rồi Kiểm tra lại.";
    }
    if (status === 413) return "File quá lớn so với giới hạn của core API (10 MB).";
    return fallback;
  }

  function run(dryRun: boolean) {
    // Lịch sử Chrome có luồng riêng (HistoryImportFlow), không đi qua action datafile/ai-logs.
    if (!file || kind === "chrome-history") return;
    const key = fileKey(file, kind);
    const form = new FormData();
    form.set("file", file);
    form.set("kind", kind);
    form.set("dry_run", dryRun ? "1" : "0");
    form.set("include_personal", includePersonal ? "1" : "0");
    if (!dryRun) {
      // Số đã Kiểm tra, không phải số người dùng gõ: core sẽ đối chiếu với thực tế.
      if (!report || checkedKey !== key) return;
      form.set("expect_replaced", String(sum(report, "replaced")));
      // Mã băm của file lúc Kiểm tra: core từ chối nếu file gửi lên khác file đã xem báo cáo.
      form.set("expect_sha256", report.file_sha256);
      form.set("import_secret", secret);
    }

    setError(null);
    startTransition(async () => {
      const result = await importToCoreAction(form);
      // Xoá mật khẩu sau MỌI lần thử Nhập thật (đúng, sai hay lỗi): không để nó nằm lại trong state.
      if (!dryRun) setSecret("");
      if (!result.ok || !result.report) {
        setError(messageFor(result.status, result.error ?? "Nhập thất bại"));
        return;
      }
      const next = result.report;
      if (dryRun) {
        setReport(next);
        setCheckedKey(key);
        setDone(null);
        setAckReplace(false);
        setAckOlder(false);
        return;
      }
      if (next.committed) {
        setDone(next);
        setReport(null);
        setCheckedKey(null);
        return;
      }
      // Core từ chối ở mức dòng (200, committed=false): buộc Kiểm tra lại.
      setReport(next);
      setCheckedKey(null);
      setAckReplace(false);
      setAckOlder(false);
      if (next.issues.some((i) => i.code === "replace_count_mismatch")) {
        setError("Dữ liệu trong Postgres đã thay đổi sau lần Kiểm tra, hãy Kiểm tra lại.");
      } else if (next.issues.some((i) => i.code === "file_changed_since_dry_run")) {
        setError("File gửi lên khác với file đã Kiểm tra. Hãy Kiểm tra lại rồi mới Nhập thật.");
      } else {
        setError("Core từ chối nhập, không có gì được ghi. Xem các lỗi bên dưới rồi Kiểm tra lại.");
      }
    });
  }

  const replaced = report ? sum(report, "replaced") : 0;
  const older = report ? sum(report, "replaced_older") : 0;
  const sameFile = !!file && checkedKey === fileKey(file, kind);
  const canCommit =
    !pending &&
    sameFile &&
    !!report &&
    report.dry_run &&
    report.errors === 0 &&
    secret.length > 0 &&
    (replaced === 0 || ackReplace) &&
    (older === 0 || ackOlder);

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4">
      <h2 className="text-sm font-semibold">Chuyển dữ liệu JSON vào Postgres</h2>
      <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
        Bấm <strong>Kiểm tra</strong> để xem báo cáo, chưa ghi gì. Bản ghi trùng id (hoặc trùng
        khoá tự nhiên) sẽ bị <strong>ghi đè</strong> bằng nội dung file; không có gì bị xoá. Tối đa 8 MB.
      </p>
      <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
        Trước lần nhập đầu tiên nên chạy <code>pg_dump</code> để có bản sao lưu.
      </p>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="core-import-kind" className={LABEL_CLASS}>
            Loại file
          </label>
          <select
            id="core-import-kind"
            value={kind}
            disabled={pending}
            onChange={(event) => {
              setKind(event.target.value as Kind);
              resetResult();
            }}
            className={INPUT_CLASS}
          >
            {KIND_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="core-import-file" className={LABEL_CLASS}>
            File
          </label>
          <input
            id="core-import-file"
            type="file"
            accept=".json,application/json"
            disabled={pending}
            onChange={onFileChange}
            className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm file:mr-3 file:rounded file:border-0 file:bg-[var(--color-surface-hover)] file:px-2 file:py-1 file:text-xs file:text-[var(--color-ink)]"
          />
        </div>
      </div>

      {kind === "datafile" ? (
        <label className="mt-3 flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={includePersonal}
            disabled={pending}
            onChange={(e) => {
              setIncludePersonal(e.target.checked);
              resetResult();
            }}
            className="mt-1"
          />
          <span>
            Ghi đè cả task cá nhân đang có trong Postgres (mặc định tắt: task cá nhân được giữ
            nguyên)
          </span>
        </label>
      ) : null}

      {kind === "chrome-history" ? (
        // key theo file: đổi file thì state kiểm tra/mật khẩu của luồng lịch sử được dựng lại sạch.
        <HistoryImportFlow key={file ? `${file.name}|${file.size}|${file.lastModified}` : "none"} file={file} />
      ) : null}

      <div className={kind === "chrome-history" ? "hidden" : "mt-4"}>
        <button
          type="button"
          disabled={!file || pending}
          onClick={() => run(true)}
          className="rounded-md border border-[var(--color-accent)] px-4 py-2 text-sm font-medium text-[var(--color-accent)] disabled:opacity-50"
        >
          {pending ? "Đang xử lý…" : "Kiểm tra"}
        </button>
      </div>

      {error ? (
        <p
          role="alert"
          className="mt-4 rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]"
        >
          {error}
        </p>
      ) : null}

      {report ? (
        <div className="mt-4 flex flex-col gap-4">
          {replaced > 0 ? (
            <div
              role="alert"
              className="rounded-md border-2 border-[var(--color-danger)] bg-[var(--color-danger)]/10 px-4 py-3 text-sm text-[var(--color-danger)]"
            >
              <p className="font-semibold">
                {replaced} bản ghi trong Postgres sẽ bị GHI ĐÈ bằng nội dung file.
              </p>
              {older > 0 ? (
                <p className="mt-1 font-bold">
                  {older} bản ghi trong file CŨ HƠN dữ liệu đang có: nhập sẽ làm mất thay đổi gần đây (ví
                  dụ trạng thái task đã cập nhật qua API).
                </p>
              ) : null}
            </div>
          ) : null}

          <CountsTable report={report} />
          <SkippedPersonalNote report={report} />
          <KeyChanges report={report} />
          <IssueList report={report} />
          <ReplacementList report={report} />
          <IgnoredFields report={report} />

          <div className="flex flex-col gap-2 rounded-md border border-[var(--color-border)] p-3">
            {replaced > 0 ? (
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={ackReplace}
                  onChange={(e) => setAckReplace(e.target.checked)}
                  className="mt-1"
                />
                <span>Tôi đã xem danh sách và đồng ý ghi đè {replaced} bản ghi</span>
              </label>
            ) : null}
            {older > 0 ? (
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={ackOlder}
                  onChange={(e) => setAckOlder(e.target.checked)}
                  className="mt-1"
                />
                <span>Tôi chấp nhận ghi đè {older} bản ghi mới hơn bằng dữ liệu cũ</span>
              </label>
            ) : null}
            {report.errors > 0 ? (
              <p className="text-xs text-[var(--color-danger)]">
                File còn {report.errors} lỗi, không thể nhập. Sửa file rồi Kiểm tra lại.
              </p>
            ) : null}
            {!sameFile ? (
              <p className="text-xs text-[var(--color-ink-muted)]">
                Cần Kiểm tra lại: file hoặc loại file đã đổi so với lần Kiểm tra gần nhất.
              </p>
            ) : null}
            <div>
              <label htmlFor="core-import-secret" className={LABEL_CLASS}>
                Mật khẩu nhập dữ liệu
              </label>
              <input
                id="core-import-secret"
                type="password"
                // "off" bị trình duyệt bỏ qua; "new-password" + các cờ dưới giảm việc đề nghị lưu mật khẩu.
                autoComplete="new-password"
                data-1p-ignore
                data-lpignore="true"
                value={secret}
                disabled={pending}
                onChange={(e) => setSecret(e.target.value)}
                className={INPUT_CLASS}
              />
              <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
                Là giá trị <code>IMPORT_COMMIT_SECRET</code> trong <code>.env</code> của core (
                <code>make env</code> sinh sẵn; <code>.env</code> có từ trước thì tự thêm biến này
                rồi khởi động lại api). Chỉ cần khi Nhập thật, không cần khi Kiểm tra.
              </p>
            </div>
            <div>
              <button
                type="button"
                disabled={!canCommit}
                onClick={() => run(false)}
                className={`rounded-md px-4 py-2 text-sm font-medium text-white disabled:opacity-40 ${
                  replaced > 0 ? "bg-[var(--color-danger)]" : "bg-[var(--color-accent)]"
                }`}
              >
                {pending ? "Đang nhập…" : "Nhập thật"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {done ? (
        <div
          role="status"
          className="mt-4 rounded-md border border-[var(--color-success)]/40 bg-[var(--color-success)]/10 px-3 py-2 text-sm"
        >
          <p className="text-[var(--color-success)]">Đã nhập xong vào Postgres.</p>
          <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
            Mã lần nhập (import_id): <code>{done.import_id}</code>. Kiểm tra lại cùng file sẽ thấy 0 tạo
            mới, 0 ghi đè.
          </p>
          <CountsTable report={done} />
          <SkippedPersonalNote report={done} />
        </div>
      ) : null}
    </section>
  );
}

/** Bảng đếm theo thực thể: nhận / tạo mới / ghi đè / không đổi / thùng rác / lỗi. */
function CountsTable({ report }: { report: ImportReport }) {
  const rows = Object.entries(report.counts).filter(([, c]) => c.received > 0 || c.invalid > 0);
  if (rows.length === 0) {
    return <p className="text-xs text-[var(--color-ink-muted)]">File không có bản ghi nào.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-[var(--color-ink-muted)]">
          <tr>
            <th className="py-1 pr-3 font-medium">Thực thể</th>
            <th className="px-2 py-1 text-right font-medium">Nhận</th>
            <th className="px-2 py-1 text-right font-medium">Tạo mới</th>
            <th className="px-2 py-1 text-right font-medium">Ghi đè</th>
            <th className="px-2 py-1 text-right font-medium">Không đổi</th>
            <th className="px-2 py-1 text-right font-medium">Thùng rác</th>
            <th className="px-2 py-1 text-right font-medium">Cá nhân (giữ)</th>
            <th className="px-2 py-1 text-right font-medium">Lỗi</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, c]) => (
            <tr key={name} className="border-t border-[var(--color-border)]/50">
              <td className="py-1 pr-3">{ENTITY_LABELS[name] ?? name}</td>
              <td className="px-2 py-1 text-right">{c.received}</td>
              <td className="px-2 py-1 text-right">{c.created}</td>
              <td
                className={`px-2 py-1 text-right ${c.replaced > 0 ? "font-semibold text-[var(--color-danger)]" : ""}`}
              >
                {c.replaced}
              </td>
              <td className="px-2 py-1 text-right">{c.unchanged}</td>
              <td className="px-2 py-1 text-right">{c.skipped_trash + c.skipped_trash_in_db}</td>
              <td className="px-2 py-1 text-right">{c.skipped_personal}</td>
              <td className={`px-2 py-1 text-right ${c.invalid > 0 ? "text-[var(--color-danger)]" : ""}`}>
                {c.invalid}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Báo số task cá nhân trong Postgres được giữ nguyên, để không ai tưởng file đã ghi đè chúng. */
function SkippedPersonalNote({ report }: { report: ImportReport }) {
  const skipped = report.counts.tasks?.skipped_personal ?? 0;
  if (skipped <= 0) return null;
  return (
    <p className="text-xs text-[var(--color-ink-muted)]">
      {skipped} task cá nhân trong Postgres được giữ nguyên (không bị file ghi đè).
    </p>
  );
}

function KeyChanges({ report }: { report: ImportReport }) {
  if (report.project_key_changes.length === 0) return null;
  return (
    <div className="text-xs">
      <p className="font-medium">Key project được chuẩn hoá ({report.project_key_changes.length})</p>
      <ul className="mt-1 list-disc pl-5 text-[var(--color-ink-muted)]">
        {report.project_key_changes.map((k, i) => (
          <li key={`${k.original}-${i}`}>
            <code>{k.original}</code> → <code>{k.normalized}</code>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Lỗi trước cảnh báo, tối đa 50 dòng; phần còn lại thu gọn trong một mục mở được. */
function IssueList({ report }: { report: ImportReport }) {
  if (report.issues.length === 0) return null;
  const sorted: ImportIssue[] = [
    ...report.issues.filter((i) => i.level === "error"),
    ...report.issues.filter((i) => i.level !== "error"),
  ];
  const head = sorted.slice(0, MAX_ISSUES_SHOWN);
  const rest = sorted.slice(MAX_ISSUES_SHOWN);
  return (
    <div className="text-xs">
      <p className="font-medium">
        {report.errors} lỗi, {report.warnings} cảnh báo
      </p>
      <ul className="mt-1 flex flex-col gap-1">
        {head.map((issue, i) => (
          <IssueRow key={i} issue={issue} />
        ))}
      </ul>
      {rest.length > 0 ? (
        <details className="mt-1">
          <summary className="cursor-pointer text-[var(--color-ink-muted)]">
            Xem thêm {rest.length} dòng
          </summary>
          <ul className="mt-1 flex flex-col gap-1">
            {rest.map((issue, i) => (
              <IssueRow key={i} issue={issue} />
            ))}
          </ul>
        </details>
      ) : null}
      {report.issues_truncated ? (
        <p className="mt-1 text-[var(--color-ink-muted)]">Core đã cắt bớt danh sách; còn nhiều dòng khác.</p>
      ) : null}
    </div>
  );
}

function IssueRow({ issue }: { issue: ImportIssue }) {
  const isError = issue.level === "error";
  return (
    <li className={isError ? "text-[var(--color-danger)]" : "text-[var(--color-ink-muted)]"}>
      <span className="font-medium">{isError ? "Lỗi" : "Cảnh báo"}</span>{" "}
      [{ENTITY_LABELS[issue.entity] ?? issue.entity}
      {issue.index !== null && issue.index !== undefined ? ` #${issue.index}` : ""}] {issue.message}{" "}
      <code>{issue.code}</code>
    </li>
  );
}

/** Danh sách bản ghi sẽ bị ghi đè, nhóm theo thực thể, mỗi bản ghi mở ra bảng diff. */
function ReplacementList({ report }: { report: ImportReport }) {
  if (report.replacements.length === 0) return null;
  const groups = new Map<string, Replacement[]>();
  for (const r of report.replacements) {
    const list = groups.get(r.entity) ?? [];
    list.push(r);
    groups.set(r.entity, list);
  }
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium">Bản ghi sẽ bị ghi đè</p>
      {Array.from(groups.entries()).map(([entity, items]) => (
        <details key={entity} className="rounded-md border border-[var(--color-border)] p-2">
          <summary className="cursor-pointer text-xs font-medium">
            {ENTITY_LABELS[entity] ?? entity} ({items.length})
          </summary>
          <div className="mt-2 flex flex-col gap-2">
            {items.map((r) => (
              <details key={`${r.entity}-${r.id}`} className="rounded border border-[var(--color-border)]/60 p-2">
                <summary className="cursor-pointer text-xs">
                  <span>{r.label}</span>
                  {r.matched_by === "natural_key" ? (
                    <span className="ml-2 text-[var(--color-ink-muted)]">(khớp theo khoá tự nhiên)</span>
                  ) : null}
                  {r.file_older_than_db ? (
                    <span className="ml-2 rounded bg-[var(--color-danger)]/15 px-1.5 py-0.5 font-medium text-[var(--color-danger)]">
                      File cũ hơn dữ liệu hiện tại
                    </span>
                  ) : null}
                </summary>
                <table className="mt-2 w-full text-left text-xs">
                  <thead className="text-[var(--color-ink-muted)]">
                    <tr>
                      <th className="py-1 pr-2 font-medium">Trường</th>
                      <th className="px-2 py-1 font-medium">Hiện tại</th>
                      <th className="px-2 py-1 font-medium">Sau khi nhập</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.changes.map((c) => (
                      <tr key={c.field} className="border-t border-[var(--color-border)]/50 align-top">
                        <td className="py-1 pr-2">
                          <code>{c.field}</code>
                        </td>
                        <td className="break-all px-2 py-1">{show(c.old)}</td>
                        <td className="break-all px-2 py-1">{show(c.new)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            ))}
          </div>
        </details>
      ))}
      {report.replacements_truncated ? (
        <p className="text-xs text-[var(--color-danger)]">
          Danh sách bị cắt bớt: còn bản ghi bị ghi đè không hiện ở đây. Số đếm ở bảng trên vẫn là đủ.
        </p>
      ) : null}
    </div>
  );
}

function IgnoredFields({ report }: { report: ImportReport }) {
  const entries = Object.entries(report.ignored_fields).filter(([, v]) => v.length > 0);
  if (entries.length === 0) return null;
  return (
    <div className="text-xs text-[var(--color-ink-muted)]">
      <p className="font-medium">Trường trong file bị bỏ qua</p>
      <ul className="mt-1 list-disc pl-5">
        {entries.map(([entity, fields]) => (
          <li key={entity}>
            {ENTITY_LABELS[entity] ?? entity}: {fields.join(", ")}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Luồng nhập chrome-history.json: Kiểm tra (dry-run) rồi Nhập thật với mật khẩu.
 *
 * Khác datafile: upsert của core chỉ lấy số lớn hơn, không ghi đè xuống và không xoá,
 * nên không có diff ghi đè hay expect_replaced; vẫn đòi mật khẩu vì lịch sử duyệt web
 * là dữ liệu nhạy cảm. Mật khẩu chỉ nằm trong state, xoá sau mỗi lần thử Nhập thật.
 */
function HistoryImportFlow({ file }: { file: File | null }) {
  const [profile, setProfile] = useState("Default");
  const [secret, setSecret] = useState("");
  const [report, setReport] = useState<BrowserHistoryImportReport | null>(null);
  const [checkedProfile, setCheckedProfile] = useState<string | null>(null);
  const [done, setDone] = useState<BrowserHistoryImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function run(dryRun: boolean) {
    if (!file) return;
    const form = new FormData();
    form.set("file", file);
    form.set("dry_run", dryRun ? "1" : "0");
    form.set("profile", profile.trim() || "Default");
    if (!dryRun) form.set("import_secret", secret);
    setError(null);
    startTransition(async () => {
      const result = await importChromeHistoryToCoreAction(form);
      if (!dryRun) setSecret("");
      if (!result.ok || !result.report) {
        setError(result.error ?? "Nhập thất bại");
        return;
      }
      if (dryRun) {
        setReport(result.report);
        setCheckedProfile(profile.trim() || "Default");
        setDone(null);
      } else {
        setDone(result.report);
        setReport(null);
        setCheckedProfile(null);
      }
    });
  }

  const sameProfile = checkedProfile === (profile.trim() || "Default");
  const canCommit = !pending && !!report && sameProfile && secret.length > 0;

  return (
    <div className="mt-4 flex flex-col gap-3">
      <div>
        <label htmlFor="history-import-profile" className={LABEL_CLASS}>
          Profile gán cho file (tên thư mục, vd Default, Profile 1)
        </label>
        <input
          id="history-import-profile"
          type="text"
          value={profile}
          maxLength={200}
          disabled={pending}
          onChange={(e) => setProfile(e.target.value)}
          className={INPUT_CLASS}
        />
      </div>
      <div>
        <button
          type="button"
          disabled={!file || pending}
          onClick={() => run(true)}
          className="rounded-md border border-[var(--color-accent)] px-4 py-2 text-sm font-medium text-[var(--color-accent)] disabled:opacity-50"
        >
          {pending ? "Đang xử lý…" : "Kiểm tra"}
        </button>
      </div>

      {error ? (
        <p
          role="alert"
          className="rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-sm text-[var(--color-danger)]"
        >
          {error}
        </p>
      ) : null}

      {report ? (
        <div className="flex flex-col gap-3 rounded-md border border-[var(--color-border)] p-3">
          <HistoryCounts report={report} />
          <p className="text-xs text-[var(--color-ink-muted)]">
            Giờ trong file được hiểu là giờ hiển thị của hệ thống. URL bỏ query string và fragment
            trước khi lưu. Chỉ tăng, không xoá và không ghi đè xuống.
          </p>
          {!sameProfile ? (
            <p className="text-xs text-[var(--color-ink-muted)]">Đã đổi profile, cần Kiểm tra lại.</p>
          ) : null}
          <div>
            <label htmlFor="history-import-secret" className={LABEL_CLASS}>
              Mật khẩu nhập dữ liệu
            </label>
            <input
              id="history-import-secret"
              type="password"
              autoComplete="new-password"
              data-1p-ignore
              data-lpignore="true"
              value={secret}
              disabled={pending}
              onChange={(e) => setSecret(e.target.value)}
              className={INPUT_CLASS}
            />
            <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
              Là giá trị <code>IMPORT_COMMIT_SECRET</code> của core. Chỉ cần khi Nhập thật.
            </p>
          </div>
          <div>
            <button
              type="button"
              disabled={!canCommit}
              onClick={() => run(false)}
              className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              {pending ? "Đang nhập…" : "Nhập thật"}
            </button>
          </div>
        </div>
      ) : null}

      {done ? (
        <div
          role="status"
          className="rounded-md border border-[var(--color-success)]/40 bg-[var(--color-success)]/10 px-3 py-2 text-sm"
        >
          <p className="text-[var(--color-success)]">Đã nhập lịch sử Chrome vào Postgres.</p>
          <HistoryCounts report={done} />
        </div>
      ) : null}
    </div>
  );
}

function HistoryCounts({ report }: { report: BrowserHistoryImportReport }) {
  return (
    <p className="text-xs">
      Profile <code>{report.profile}</code>: nhận {report.received}, tạo mới {report.created}, cập
      nhật {report.updated}, không đổi {report.unchanged}
      {report.invalid > 0 ? (
        <span className="text-[var(--color-danger)]">, bỏ qua {report.invalid} dòng không hợp lệ</span>
      ) : null}
      .
    </p>
  );
}
