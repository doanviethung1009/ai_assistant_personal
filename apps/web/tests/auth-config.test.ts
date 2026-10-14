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
});
