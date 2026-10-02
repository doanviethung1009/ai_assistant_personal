import Link from "next/link";

import { ApiErrorPanel } from "@/components/api-error";
import { SensitiveToggle } from "@/components/sensitive-toggle";
import { DATA_SOURCE, getHealth, getSystemInfo, IS_LOCAL } from "@/lib/api";
import { dataFilePath } from "@/lib/store/json-file";
import type { ComponentHealth } from "@/lib/types";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Thông tin hệ thống · Builder AI Assistant",
};

const SECTIONS = [
  { id: "health", label: "Tình trạng" },
  { id: "config", label: "Cấu hình" },
  { id: "containers", label: "Container" },
  { id: "accounts", label: "Tài khoản" },
  { id: "deploy", label: "Deploy" },
];

/**
 * Danh sách tài khoản/khoá quản trị của hệ thống.
 *
 * KHÔNG có "mật khẩu mặc định" kiểu admin/admin123 ở đâu trong code — mọi
 * secret được `scripts/gen-env.sh` sinh ngẫu nhiên bằng `openssl rand` ngay
 * lần đầu chạy `make env`/`make bootstrap`, khác nhau mỗi lần chạy, mỗi máy.
 * Chỉ Grafana có USERNAME cố định ("admin") vì đó là hành vi mặc định của
 * chính image Grafana, không phải do dự án đặt.
 *
 * Bảng này CHỦ Ý không có cột "giá trị" — chỉ có tên biến và lệnh để người
 * có quyền truy cập shell/.env tự tra, giữ đúng nguyên tắc không render
 * secret ra web (xem docstring SystemPage).
 */
interface AccountInfo {
  system: string;
  username: string | null;
  envVar: string;
  lookupCommand: string;
  note?: string;
}

const ACCOUNTS: AccountInfo[] = [
  {
    system: "Core API",
    username: null,
    envVar: "API_KEY",
    lookupCommand: "grep API_KEY .env",
    note: "Không có username — một khoá tĩnh dùng cho header X-API-Key.",
  },
  {
    system: "Postgres",
    username: "giá trị POSTGRES_USER (mặc định builder)",
    envVar: "POSTGRES_PASSWORD",
    lookupCommand: "grep POSTGRES .env",
  },
  {
    system: "Grafana",
    username: "admin",
    envVar: "GRAFANA_ADMIN_PASSWORD",
    lookupCommand: "grep GRAFANA_ADMIN_PASSWORD .env",
    note: 'Username "admin" là mặc định của chính Grafana, không đổi được qua .env của dự án này.',
  },
  {
    system: "LiteLLM (profile llm)",
    username: null,
    envVar: "LITELLM_MASTER_KEY",
    lookupCommand: "grep LITELLM_MASTER_KEY .env",
    note: "Không có username — master key dạng sk-..., dùng cho header Authorization.",
  },
  {
    system: "Web (Next.js)",
    username: null,
    envVar: "(không có)",
    lookupCommand: "—",
    note: "Chưa có đăng nhập ở Phase 1. Ai mở được URL thì dùng app như chủ sở hữu — xem cảnh báo ở mục Deploy.",
  },
];

/**
 * Mô tả tĩnh các service Docker Compose, để người xem trang biết đang có gì
 * đang chạy mà không phải mở docker-compose.yml. KHÔNG đọc port/tên thật từ
 * biến môi trường ở đây — cổng thật có thể bị người quản trị đổi qua .env,
 * và trang này không có cách nào biết compose đang dùng profile nào. Mục
 * đích là giải thích VAI TRÒ của từng service, số cổng chỉ là giá trị mặc
 * định tham khảo (khớp .env.example) để dễ nhận ra khi đọc log hay chạy
 * `docker compose ps`.
 */
interface ContainerInfo {
  name: string;
  image: string;
  role: string;
  defaultPort: string | null;
  profile: "mặc định" | "llm" | "monitoring";
}

const CONTAINERS: ContainerInfo[] = [
  {
    name: "builder-postgres",
    image: "pgvector/pgvector:pg17",
    role: "Lưu toàn bộ dữ liệu nghiệp vụ: task, project, note, nhật ký thay đổi.",
    defaultPort: "5432",
    profile: "mặc định",
  },
  {
    name: "builder-redis",
    image: "redis:7.4-alpine",
    role: "Đếm rate limit theo cửa sổ 60s. Không lưu dữ liệu nghiệp vụ.",
    defaultPort: "6379",
    profile: "mặc định",
  },
  {
    name: "builder-api",
    image: "builder-ai-api (build từ apps/core)",
    role: "FastAPI — toàn bộ logic nghiệp vụ, xác thực X-API-Key, migration Alembic chạy tự động lúc khởi động.",
    defaultPort: "8000",
    profile: "mặc định",
  },
  {
    name: "builder-web",
    image: "builder-ai-web (build từ apps/web)",
    role: "Next.js — giao diện. API key chỉ tồn tại ở đây, phía server, không xuống trình duyệt.",
    defaultPort: "3000",
    profile: "mặc định",
  },
  {
    name: "builder-litellm",
    image: "ghcr.io/berriai/litellm:main-stable",
    role: "Gateway LLM — mọi lời gọi model đi qua đây để theo dõi chi phí một chỗ. Chưa dùng ở Phase 1.",
    defaultPort: "4000",
    profile: "llm",
  },
  {
    name: "builder-prometheus",
    image: "prom/prometheus:v3.1.0",
    role: "Scrape /metrics của api và các exporter, lưu timeseries 30 ngày.",
    defaultPort: "9090",
    profile: "monitoring",
  },
  {
    name: "builder-grafana",
    image: "grafana/grafana:11.5.1",
    role: "Dashboard đọc dữ liệu từ Prometheus.",
    defaultPort: "3001",
    profile: "monitoring",
  },
  {
    name: "builder-blackbox",
    image: "prom/blackbox-exporter:v0.26.0",
    role: "Probe HTTP/TCP từ ngoài vào — nền của healthcheck, cảnh báo TLS sắp hết hạn.",
    defaultPort: "9115",
    profile: "monitoring",
  },
  {
    name: "builder-postgres-exporter",
    image: "prometheuscommunity/postgres-exporter:v0.16.0",
    role: "Số liệu kết nối, transaction, kích thước bảng của Postgres. Không publish port ra host.",
    defaultPort: null,
    profile: "monitoring",
  },
  {
    name: "builder-node-exporter",
    image: "prom/node-exporter:v1.8.2",
    role: "RAM/CPU/disk của host. Cần Linux Engine thật, lỗi trên Docker Desktop Windows/macOS.",
    defaultPort: null,
    profile: "monitoring",
  },
  {
    name: "builder-cadvisor",
    image: "gcr.io/cadvisor/cadvisor:v0.52.1",
    role: "CPU/RAM/network theo từng container.",
    defaultPort: null,
    profile: "monitoring",
  },
];

const PROFILE_STYLES: Record<ContainerInfo["profile"], string> = {
  "mặc định": "text-[var(--color-accent)]",
  llm: "text-[var(--color-warn)]",
  monitoring: "text-[var(--color-success)]",
};

/**
 * Trang Thông tin hệ thống / Quản trị.
 *
 * NGUYÊN TẮC AN TOÀN cho trang này — đọc trước khi thêm field mới:
 *   1. KHÔNG BAO GIỜ render giá trị thật của secret (API_KEY, DATABASE_URL,
 *      LITELLM_MASTER_KEY, mật khẩu Postgres/Grafana). Trang này không có
 *      cơ chế đăng nhập riêng — bất kỳ ai mở được URL /system trên trình
 *      duyệt đã đăng nhập Next.js (hoặc qua LAN, xem docker-compose.lan.yml)
 *      đều xem được mọi thứ ở đây.
 *   2. Mọi field hiển thị phải tới từ app/schemas/system.py::SystemInfo ở
 *      backend — schema đó là nơi quyết định field nào "đủ an toàn để lộ
 *      cho ai xem được trang này", không phải quyết định ở component.
 *      Thêm field mới thì sửa SystemInfo trước, chạy `make gen-types`, rồi
 *      mới render ở đây.
 *   3. SensitiveToggle chỉ dùng cho thông tin "nội bộ nhưng không mật"
 *      (URL nội bộ, tên biến môi trường) — không phải để biện minh cho việc
 *      hiện secret thật sau một cú click.
 */
export default async function SystemPage() {
  let health: Awaited<ReturnType<typeof getHealth>>;
  let info: Awaited<ReturnType<typeof getSystemInfo>>;

  try {
    [health, info] = await Promise.all([getHealth(), getSystemInfo()]);
  } catch (error) {
    return (
      <ApiErrorPanel
        message={error instanceof Error ? error.message : String(error)}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">
          Thông tin hệ thống
        </h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Trạng thái và cấu hình vận hành của core API. Trang này không hiển
          thị secret — xem{" "}
          <Link href="/docs?doc=ops" className="text-[var(--color-accent)] underline">
            bản đồ code
          </Link>{" "}
          nếu cần biết nơi cấu hình thật nằm ở đâu.
        </p>
      </div>

      <nav aria-label="Mục lục">
        <ul className="flex flex-wrap gap-2">
          {SECTIONS.map((section) => (
            <li key={section.id}>
              <a
                href={`#${section.id}`}
                className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-1.5 text-xs transition-colors hover:bg-[var(--color-surface-hover)]"
              >
                {section.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      {/* ── Tình trạng ──────────────────────────────────────────────── */}
      <section id="health" className="scroll-mt-6">
        <h2 className="text-sm font-semibold">Tình trạng</h2>

        {IS_LOCAL ? (
          <p className="mt-2 rounded-md border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10 px-3 py-2 text-xs text-[var(--color-warn)]">
            Đang chạy ở chế độ <code>DATA_SOURCE={DATA_SOURCE}</code>, không có
            core API thật để hỏi tình trạng. Phần này chỉ áp dụng khi
            <code> DATA_SOURCE=api</code>.
          </p>
        ) : health === null ? (
          <p className="mt-2 rounded-md border border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 px-3 py-2 text-xs text-[var(--color-danger)]">
            Không gọi được <code>/health/ready</code>. Core API có thể đang
            down — kiểm tra bằng <code>docker compose ps</code>.
          </p>
        ) : (
          <div className="mt-2 flex flex-col gap-3">
            <div
              className={`rounded-lg border p-4 ${health.status === "ok"
                ? "border-[var(--color-success)]/40 bg-[var(--color-success)]/10"
                : "border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10"
                }`}
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p
                  className={`text-sm font-semibold ${health.status === "ok"
                    ? "text-[var(--color-success)]"
                    : "text-[var(--color-warn)]"
                    }`}
                >
                  {health.status === "ok" ? "Hoạt động bình thường" : "Suy giảm"}
                </p>
                <code className="rounded bg-black/30 px-1.5 py-0.5 text-xs">
                  v{health.version} · {health.environment}
                </code>
              </div>
            </div>

            <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {Object.entries(health.components).map(([name, component]) => (
                <ComponentCard key={name} name={name} component={component} />
              ))}
            </dl>
          </div>
        )}
      </section>

      {/* ── Cấu hình ────────────────────────────────────────────────── */}
      <section id="config" className="scroll-mt-6">
        <h2 className="text-sm font-semibold">Cấu hình</h2>

        {info === null ? (
          <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
            {IS_LOCAL
              ? "Không áp dụng ở chế độ file/memory."
              : "Không đọc được. Core API có thể đang down."}
          </p>
        ) : (
          <dl className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <ConfigItem label="Tên ứng dụng" value={info.app_name} />
            <ConfigItem label="Môi trường" value={info.environment} />
            <ConfigItem
              label="Timezone hiển thị"
              value={info.display_timezone}
            />
            <ConfigItem
              label="Giữ thùng rác"
              value={`${info.trash_retention_days} ngày`}
            />
            <ConfigItem
              label="Rate limit"
              value={
                info.rate_limit_enabled
                  ? `${info.rate_limit_requests_per_minute} request/phút`
                  : "Đang tắt"
              }
            />
            <ConfigItem
              label="CORS cho phép"
              value={info.cors_origins.join(", ") || "(trống)"}
            />
          </dl>
        )}

        <div className="mt-3">
          <SensitiveToggle label="Thông tin nội bộ — URL và biến môi trường đang dùng (không phải secret)">
            <dl className="flex flex-col gap-2 text-xs">
              <div className="flex flex-wrap gap-1.5">
                <dt className="text-[var(--color-ink-muted)]">Nguồn dữ liệu web:</dt>
                <dd>
                  <code className="rounded bg-black/30 px-1">
                    DATA_SOURCE={DATA_SOURCE}
                  </code>
                </dd>
              </div>
              {DATA_SOURCE === "file" ? (
                <div className="flex flex-wrap gap-1.5">
                  <dt className="text-[var(--color-ink-muted)]">File dữ liệu:</dt>
                  <dd className="break-all">
                    <code className="rounded bg-black/30 px-1">
                      {dataFilePath()}
                    </code>
                  </dd>
                </div>
              ) : null}
              <p className="text-[var(--color-ink-muted)]">
                Khoá API, chuỗi kết nối database, và mọi secret khác
                KHÔNG hiển thị ở đây hay bất kỳ đâu trên web — chúng chỉ tồn
                tại trong process Next.js phía server
                (<code>apps/web/lib/api.ts</code>, có{" "}
                <code>&quot;server-only&quot;</code>) và không bao giờ được
                gửi xuống trình duyệt.
              </p>
            </dl>
          </SensitiveToggle>
        </div>
      </section>

      {/* ── Container ───────────────────────────────────────────────── */}
      <section id="containers" className="scroll-mt-6">
        <h2 className="text-sm font-semibold">Container Docker</h2>
        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Toàn hệ thống chạy bằng Docker Compose trên một node, chia ba
          profile. Profile <code>mặc định</code> là thứ tối thiểu để dùng
          được; <code>llm</code> và <code>monitoring</code> bật thêm khi cần.
          Cổng ghi dưới đây là giá trị mặc định (khớp <code>.env.example</code>),
          có thể đã bị đổi qua <code>.env</code> trên máy này — kiểm tra thật
          bằng <code>docker compose ps</code>.
        </p>

        <div className="mt-3 overflow-x-auto rounded-lg border border-[var(--color-border)]">
          <table className="w-full border-collapse text-sm">
            <thead className="bg-white/5">
              <tr className="border-b border-[var(--color-border)]">
                <th className="px-3 py-2 text-left text-xs font-semibold">
                  Container
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold">
                  Vai trò
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold">
                  Cổng mặc định
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold">
                  Profile
                </th>
              </tr>
            </thead>
            <tbody>
              {CONTAINERS.map((container) => (
                <tr
                  key={container.name}
                  className="border-b border-[var(--color-border)] last:border-0"
                >
                  <td className="px-3 py-2 align-top">
                    <code className="text-xs">{container.name}</code>
                    <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
                      {container.image}
                    </p>
                  </td>
                  <td className="px-3 py-2 align-top text-xs text-[var(--color-ink-muted)]">
                    {container.role}
                  </td>
                  <td className="px-3 py-2 align-top text-xs">
                    {container.defaultPort ? (
                      <code>127.0.0.1:{container.defaultPort}</code>
                    ) : (
                      <span className="text-[var(--color-ink-muted)]">
                        không publish
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 align-top text-xs">
                    <span className={PROFILE_STYLES[container.profile]}>
                      {container.profile}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Mọi cổng chỉ bind <code>127.0.0.1</code>, không hở ra LAN theo mặc
          định. Muốn mở <code>web</code> cho máy khác trong nhà dùng chung,
          xem mục Deploy bên dưới.
        </p>
      </section>

      {/* ── Tài khoản ───────────────────────────────────────────────── */}
      <section id="accounts" className="scroll-mt-6">
        <h2 className="text-sm font-semibold">Tài khoản quản trị</h2>
        <p className="mt-2 rounded-md border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10 px-3 py-2 text-xs text-[var(--color-warn)]">
          Không có mật khẩu mặc định đặt sẵn trong code (không có kiểu
          admin/admin123). Mọi khoá được <code>scripts/gen-env.sh</code> sinh
          ngẫu nhiên bằng <code>openssl rand</code> ngay lần đầu chạy{" "}
          <code>make env</code> hoặc <code>make bootstrap</code> — khác nhau
          mỗi lần chạy, mỗi máy. Bảng dưới chỉ ghi tên biến và lệnh để tự tra
          giá trị thật, không hiển thị giá trị ở đây.
        </p>

        <div className="mt-3 overflow-x-auto rounded-lg border border-[var(--color-border)]">
          <table className="w-full border-collapse text-sm">
            <thead className="bg-white/5">
              <tr className="border-b border-[var(--color-border)]">
                <th className="px-3 py-2 text-left text-xs font-semibold">
                  Hệ thống
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold">
                  Username
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold">
                  Tra mật khẩu/khoá
                </th>
              </tr>
            </thead>
            <tbody>
              {ACCOUNTS.map((account) => (
                <tr
                  key={account.system}
                  className="border-b border-[var(--color-border)] last:border-0"
                >
                  <td className="px-3 py-2 align-top text-xs font-medium">
                    {account.system}
                    {account.note ? (
                      <p className="mt-0.5 font-normal text-[var(--color-ink-muted)]">
                        {account.note}
                      </p>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 align-top text-xs text-[var(--color-ink-muted)]">
                    {account.username ?? "—"}
                  </td>
                  <td className="px-3 py-2 align-top text-xs">
                    {account.lookupCommand === "—" ? (
                      <span className="text-[var(--color-ink-muted)]">—</span>
                    ) : (
                      <code className="rounded bg-black/30 px-1.5 py-0.5">
                        {account.lookupCommand}
                      </code>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Lệnh tra phải chạy trên máy đang host container, nơi có quyền đọc{" "}
          <code>.env</code> (chmod 600, chỉ user đã dựng stack đọc được).
          Đổi một khoá: sửa dòng tương ứng trong <code>.env</code> rồi{" "}
          <code>docker compose up -d</code> lại service dùng khoá đó — xem
          Case 4 trong{" "}
          <Link href="/docs?doc=deploy" className="text-[var(--color-accent)] underline">
            Runbook deploy
          </Link>
          .
        </p>
      </section>

      {/* ── Deploy ──────────────────────────────────────────────────── */}
      <section id="deploy" className="scroll-mt-6">
        <h2 className="text-sm font-semibold">Deploy</h2>
        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Hướng dẫn đầy đủ nằm trong tài liệu repo, đọc trực tiếp ở đây —
          không phải bản chép lại.
        </p>
        <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <DeployLink
            href="/docs?doc=guide"
            title="Chia sẻ trong LAN"
            note="Cho máy khác trong nhà dùng chung, không cần dựng server riêng. make lan-up / make lan-down."
          />
          <DeployLink
            href="/docs?doc=deploy"
            title="Runbook deploy"
            note="Thứ tự lệnh cho từng tình huống: lần đầu, update có migration, hotfix, rollback."
          />
          <DeployLink
            href="/docs?doc=gitflow"
            title="Mô hình Git và go-live"
            note="main → uat → prod, chỉ fast-forward. Lý do chọn mô hình này."
          />
          <DeployLink
            href="/docs?doc=ops"
            title="Bản đồ code"
            note="Vị trí từng thành phần, bảng lệnh Makefile."
          />
        </ul>
      </section>

      <section className="rounded-lg border border-dashed border-[var(--color-border)] p-4">
        <h2 className="text-sm font-semibold">Liên quan</h2>
        <p className="mt-2 text-xs text-[var(--color-ink-muted)]">
          Xem cách các container nói với nhau ở{" "}
          <Link href="/architecture" className="text-[var(--color-accent)] underline">
            Kiến trúc
          </Link>
          , hoặc tiến độ từng giai đoạn ở{" "}
          <Link href="/roadmap" className="text-[var(--color-accent)] underline">
            Lộ trình
          </Link>
          .
        </p>
      </section>
    </div>
  );
}

function ComponentCard({
  name,
  component,
}: {
  name: string;
  component: ComponentHealth;
}) {
  const ok = component.status === "ok";
  return (
    <div
      className={`rounded-md border px-3 py-2 ${ok
        ? "border-[var(--color-border)] bg-[var(--color-surface-raised)]"
        : "border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10"
        }`}
    >
      <div className="flex items-center justify-between gap-2">
        <dt className="text-sm font-medium capitalize">{name}</dt>
        <dd
          className={`text-xs font-medium ${ok ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"
            }`}
        >
          {ok ? "OK" : "Lỗi"}
        </dd>
      </div>
      {component.latency_ms != null ? (
        <p className="mt-0.5 text-xs text-[var(--color-ink-muted)]">
          {component.latency_ms.toFixed(1)} ms
        </p>
      ) : null}
      {component.error ? (
        <p className="mt-0.5 break-all text-xs text-[var(--color-danger)]">
          {component.error}
        </p>
      ) : null}
    </div>
  );
}

function ConfigItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-raised)] px-3 py-2">
      <dt className="text-xs text-[var(--color-ink-muted)]">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium">{value}</dd>
    </div>
  );
}

function DeployLink({
  href,
  title,
  note,
}: {
  href: string;
  title: string;
  note: string;
}) {
  return (
    <li>
      <Link
        href={href}
        className="block rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-3 transition-colors hover:bg-[var(--color-surface-hover)]"
      >
        <span className="block text-sm font-medium">{title}</span>
        <span className="mt-0.5 block text-xs text-[var(--color-ink-muted)]">
          {note}
        </span>
      </Link>
    </li>
  );
}
