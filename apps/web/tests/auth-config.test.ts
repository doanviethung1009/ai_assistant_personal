import { describe, expect, it } from "vitest";

import { readAuthConfig } from "@/lib/auth-config";

const GOOD = {
  AUTH_SECRET: "a".repeat(32),
  AUTH_URL: "http://localhost:3000",
  AUTH_TRUST_HOST: "true",
  AUTH_GOOGLE_ID: "id",
  AUTH_GOOGLE_SECRET: "secret",
  CORE_JWT_SECRET: "b".repeat(32),
};

describe("readAuthConfig", () => {
  it("đủ biến → ok, hd tách theo dấu phẩy", () => {
    const cfg = readAuthConfig({ ...GOOD, GOOGLE_ALLOWED_HD: "A.com, b.com" });
    expect(cfg.ok && cfg.allowedHd).toEqual(["a.com", "b.com"]);
  });

  it("thiếu biến → chỉ liệt kê tên, không lộ giá trị", () => {
    const cfg = readAuthConfig({ ...GOOD, AUTH_SECRET: "", CORE_JWT_SECRET: "short" });
    expect(cfg.ok).toBe(false);
    if (!cfg.ok) {
      expect(cfg.missing).toContain("AUTH_SECRET");
      expect(cfg.missing.some((m) => m.startsWith("CORE_JWT_SECRET"))).toBe(true);
      expect(JSON.stringify(cfg)).not.toContain("short");
    }
  });

  it("AUTH_TRUST_HOST khác true bị báo thiếu", () => {
    const cfg = readAuthConfig({ ...GOOD, AUTH_TRUST_HOST: "false" });
    expect(cfg.ok).toBe(false);
  });

  it("AUTH_URL http ngoài localhost sinh cảnh báo; localhost và https thì không", () => {
    const warn = (url: string) => {
      const cfg = readAuthConfig({ ...GOOD, AUTH_URL: url });
      return cfg.ok ? cfg.warnings.length : -1;
    };
    expect(warn("http://192.168.1.10:3000")).toBe(1);
    expect(warn("http://localhost:3000")).toBe(0);
    expect(warn("http://127.0.0.1:3000")).toBe(0);
    expect(warn("https://app.example.com")).toBe(0);
  });

  it("Google là tuỳ chọn: thiếu cả hai biến → ok nhưng googleEnabled=false", () => {
    const cfg = readAuthConfig({ ...GOOD, AUTH_GOOGLE_ID: "", AUTH_GOOGLE_SECRET: "" });
    expect(cfg.ok && cfg.googleEnabled).toBe(false);
    expect(cfg.ok && cfg.passwordEnabled).toBe(true);
  });

  it("chỉ có một trong hai biến Google là cấu hình dở → báo thiếu biến còn lại", () => {
    const cfg = readAuthConfig({ ...GOOD, AUTH_GOOGLE_SECRET: "" });
    expect(cfg.ok).toBe(false);
    if (!cfg.ok) expect(cfg.missing).toContain("AUTH_GOOGLE_SECRET");
  });

  it("tắt cả Google lẫn mật khẩu → lỗi cấu hình; chỉ tắt mật khẩu thì Google vẫn chạy", () => {
    const none = readAuthConfig({ ...GOOD, AUTH_GOOGLE_ID: "", AUTH_GOOGLE_SECRET: "", PASSWORD_LOGIN_ENABLED: "false" });
    expect(none.ok).toBe(false);
    const googleOnly = readAuthConfig({ ...GOOD, PASSWORD_LOGIN_ENABLED: "false" });
    expect(googleOnly.ok && googleOnly.googleEnabled && !googleOnly.passwordEnabled).toBe(true);
  });
});
