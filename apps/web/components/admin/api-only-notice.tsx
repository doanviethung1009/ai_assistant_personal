/** Chế độ file/memory không có đăng nhập, nên không có người dùng hay nhật ký để quản trị. */
export function ApiOnlyNotice({ title }: { title: string }) {
  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      <p
        role="note"
        className="mt-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-2 text-sm text-[var(--color-ink-muted)]"
      >
        Trang này chỉ dùng được ở chế độ Core API (<code>DATA_SOURCE=api</code>), nơi có đăng nhập và Postgres.
      </p>
    </div>
  );
}
