import { VaultClient } from "@/components/vault-client";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Két thông tin nhạy cảm",
  description:
    "Lưu mật khẩu, token, connection string được mã hoá AES-256 ngay trên trình duyệt, che mặc định và chỉ hiện khi cần.",
};

export default function VaultPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Két thông tin nhạy cảm</h1>
        <p className="mt-1 text-sm text-[var(--color-ink-muted)]">
          Thông tin hệ thống, tài khoản, token… được mã hoá bằng mật khẩu master
          ngay trên trình duyệt. Server chỉ giữ bản mã. Giá trị bí mật được che
          mặc định, bấm “Hiện” để xem tạm thời.
        </p>
      </div>
      <VaultClient />
    </div>
  );
}
