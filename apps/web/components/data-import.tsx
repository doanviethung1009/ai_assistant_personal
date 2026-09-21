"use client";

import { useRef, useState, useTransition } from "react";

import { importDataAction, type ImportActionResult } from "@/app/actions";

const INPUT_CLASS =
  "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm";
const LABEL_CLASS = "mb-1 block text-xs font-medium text-[var(--color-ink-muted)]";

const KINDS = [
  { value: "json", label: "JSON đầy đủ", accept: ".json,application/json" },
  { value: "tasks-csv", label: "CSV task", accept: ".csv,text/csv" },
  { value: "projects-csv", label: "CSV project", accept: ".csv,text/csv" },
] as const;

export function DataImport({ allowReplace }: { allowReplace: boolean }) {
  const [kind, setKind] = useState<(typeof KINDS)[number]["value"]>("json");
  const [mode, setMode] = useState<"merge" | "replace">("merge");
  const [result, setResult] = useState<ImportActionResult | null>(null);
  const [pending, startTransition] = useTransition();
  const formRef = useRef<HTMLFormElement>(null);

  const accept = KINDS.find((item) => item.value === kind)!.accept;

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResult(null);

    const formData = new FormData(event.currentTarget);
    formData.set("kind", kind);
    formData.set("mode", mode);

    startTransition(async () => {
      const response = await importDataAction(formData);
      setResult(response);
      if (response.ok) formRef.current?.reset();
    });
  }

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-4">
      <h2 className="text-sm font-semibold">Nhập dữ liệu</h2>
      <p className="mt-1 text-xs text-[var(--color-ink-muted)]">
        CSV task đối chiếu project theo cột <code>project_key</code>, không tự
        tạo project mới. Nhập CSV project trước nếu cần.
      </p>

      <form ref={formRef} onSubmit={handleSubmit} className="mt-4 flex flex-col gap-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="import-kind" className={LABEL_CLASS}>
              Loại dữ liệu
            </label>
            <select
              id="import-kind"
              value={kind}
              onChange={(event) =>
                setKind(event.target.value as (typeof KINDS)[number]["value"])
              }
              className={INPUT_CLASS}
            >
              {KINDS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="import-file" className={LABEL_CLASS}>
              File
            </label>
            <input
              id="import-file"
              name="file"
              type="file"
              required
              accept={accept}
              className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1.5 text-sm file:mr-3 file:rounded file:border-0 file:bg-[var(--color-surface-hover)] file:px-2 file:py-1 file:text-xs file:text-[var(--color-ink)]"
            />
          </div>
        </div>

        <fieldset>
          <legend className={LABEL_CLASS}>Cách ghi</legend>
          <div className="flex flex-col gap-2 sm:flex-row sm:gap-4">
            <label className="flex items-start gap-2 text-sm">
              <input
                type="radio"
                name="mode-choice"
                value="merge"
                checked={mode === "merge"}
                onChange={() => setMode("merge")}
                className="mt-1 accent-[var(--color-accent)]"
              />
              <span>
                Thêm vào
                <span className="block text-xs text-[var(--color-ink-muted)]">
                  Giữ dữ liệu hiện có, bỏ qua project trùng key
                </span>
              </span>
            </label>

            <label
              className={`flex items-start gap-2 text-sm ${
                allowReplace ? "" : "opacity-40"
              }`}
            >
              <input
                type="radio"
                name="mode-choice"
                value="replace"
                checked={mode === "replace"}
                disabled={!allowReplace}
                onChange={() => setMode("replace")}
                className="mt-1 accent-[var(--color-danger)]"
              />
              <span>
                Thay toàn bộ
                <span className="block text-xs text-[var(--color-ink-muted)]">
                  {allowReplace
                    ? "Xoá hết dữ liệu hiện tại rồi nạp lại từ file"
                    : "Bị chặn khi dữ liệu nằm trong Postgres"}
                </span>
              </span>
            </label>
          </div>
        </fieldset>

        {mode === "replace" ? (
          <p
            role="alert"
            className="rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-xs text-[var(--color-danger)]"
          >
            Thao tác này xoá vĩnh viễn dữ liệu hiện tại. Nên tải bản JSON về
            trước khi làm.
          </p>
        ) : null}

        <div>
          <button
            type="submit"
            disabled={pending}
            className="rounded-md bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {pending ? "Đang nhập…" : "Nhập"}
          </button>
        </div>
      </form>

      {result ? (
        <div
          role="status"
          className={`mt-4 rounded-md border px-3 py-2 text-sm ${
            result.ok
              ? "border-[var(--color-success)]/40 bg-[var(--color-success)]/10"
              : "border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10"
          }`}
        >
          {result.ok && result.summary ? (
            <>
              <p className="text-[var(--color-success)]">
                Đã nhập {result.summary.created_tasks} task và{" "}
                {result.summary.created_projects} project.
              </p>

              {result.summary.warnings.length > 0 ? (
                <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-[var(--color-ink-muted)]">
                  {result.summary.warnings.slice(0, 10).map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              ) : null}

              {result.summary.skipped.length > 0 ? (
                <>
                  <p className="mt-2 text-xs text-[var(--color-warn)]">
                    Bỏ qua {result.summary.skipped.length} dòng:
                  </p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-[var(--color-ink-muted)]">
                    {result.summary.skipped.slice(0, 10).map((item) => (
                      <li key={`${item.line}-${item.reason}`}>
                        dòng {item.line}: {item.reason}
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </>
          ) : (
            <p className="text-[var(--color-danger)]">{result.error}</p>
          )}
        </div>
      ) : null}
    </section>
  );
}
