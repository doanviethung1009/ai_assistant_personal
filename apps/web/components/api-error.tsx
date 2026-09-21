export function ApiErrorPanel({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 p-4"
    >
      <p className="text-sm font-medium text-[var(--color-danger)]">
        Không đọc được dữ liệu từ core API
      </p>
      <p className="mt-1 text-sm text-[var(--color-ink-muted)]">{message}</p>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-[var(--color-ink-muted)]">
        <li>
          Kiểm tra service đang chạy:{" "}
          <code className="rounded bg-black/30 px-1">docker compose ps</code>
        </li>
        <li>
          Xem log:{" "}
          <code className="rounded bg-black/30 px-1">
            docker compose logs -f api
          </code>
        </li>
        <li>
          Xác nhận <code className="rounded bg-black/30 px-1">API_KEY</code> trong
          .env khớp giữa api và web
        </li>
      </ul>
    </div>
  );
}
