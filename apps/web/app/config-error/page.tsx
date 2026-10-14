import { redirect } from "next/navigation";

import { authEnabled, readAuthConfig } from "@/lib/auth-config";

export const dynamic = "force-dynamic";

/**
 * Hiện khi DATA_SOURCE=api mà thiếu cấu hình đăng nhập (middleware rewrite về đây với 503).
 * CHỈ liệt kê TÊN biến thiếu, không bao giờ giá trị. Không gọi core.
 */
export default function ConfigErrorPage() {
  if (!authEnabled()) redirect("/");
  const cfg = readAuthConfig();
  if (cfg.ok) redirect("/");

  return (
    <div className="flex min-h-screen w-full items-center justify-center px-4">
      <div className="w-full max-w-lg rounded-xl border border-[var(--color-danger)]/40 bg-[var(--color-surface-raised)] p-8">
        <h1 className="text-lg font-semibold text-[var(--color-danger)]">Thiếu cấu hình đăng nhập</h1>
        <p className="mt-2 text-sm text-[var(--color-ink-muted)]">
          Web đang chạy ở chế độ api nên cần đăng nhập, nhưng các biến môi trường sau chưa đặt hoặc sai:
        </p>
        <ul className="mt-3 list-disc space-y-1 pl-5 font-mono text-sm text-[var(--color-ink)]">
          {cfg.missing.map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
        <p className="mt-4 text-xs text-[var(--color-ink-muted)]">
          Chạy <code>make env</code> để sinh khoá, điền AUTH_GOOGLE_ID/SECRET theo docs/GOOGLE_OAUTH_SETUP.md,
          rồi <code>docker compose up -d web</code>.
        </p>
      </div>
    </div>
  );
}
