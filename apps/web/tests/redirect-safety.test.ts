import { describe, expect, it } from "vitest";

import { safeCallbackPath } from "@/lib/redirect-safety";

const AUTH_URL = "http://localhost:3000";

describe("safeCallbackPath", () => {
  it("giữ đường dẫn nội bộ kèm query", () => {
    expect(safeCallbackPath("/tasks?x=1", AUTH_URL)).toBe("/tasks?x=1");
    expect(safeCallbackPath("/", AUTH_URL)).toBe("/");
  });

  it("nhận URL tuyệt đối cùng origin và quy về path", () => {
    expect(safeCallbackPath("http://localhost:3000/team?status=closed", AUTH_URL)).toBe("/team?status=closed");
  });

  it.each([
    ["//evil.example"],
    ["/\\evil.example"],
    ["https://evil.example"],
    ["http://localhost:3001/x"],
    ["javascript:alert(1)"],
    ["/%2F%2Fevil.example"],
    ["/%5Cevil.example"],
    ["/.//evil.com"],
    ["/..//evil.com"],
    ["/a/..//evil.com"],
    ["/%2e//evil.com"],
    ["/%2E%2E//evil.com"],
    ["/./%2F/evil.com"],
    ["/%2e/%2F"],
    ["/../%2f@"],
    ["\t/evil"],
    ["/ok\nSet-Cookie: a=b"],
    [""],
  ])("chặn %j", (input) => {
    expect(safeCallbackPath(input, AUTH_URL)).toBe("/");
  });

  it("idempotent: safe(safe(x)) === safe(x)", () => {
    const inputs = ["/tasks?x=1", "/.//evil.com", "/a/..//evil.com", "/%2e//evil.com", "//evil.example", "/a/./b/../c?q=1", "http://localhost:3000/team?x=1"];
    for (const x of inputs) {
      const once = safeCallbackPath(x, AUTH_URL);
      expect(safeCallbackPath(once, AUTH_URL)).toBe(once);
    }
  });

  it("null/undefined/chuỗi lỗi decode → /", () => {
    expect(safeCallbackPath(null, AUTH_URL)).toBe("/");
    expect(safeCallbackPath(undefined, AUTH_URL)).toBe("/");
    expect(safeCallbackPath("/%E0%A4%A", AUTH_URL)).toBe("/");
  });

  it("fuzz (seed cố định): idempotent và luôn bắt đầu bằng đúng một '/' không theo sau bởi '/' hay '\\'", () => {
    const pieces = ["/", ".", "..", "%2F", "%2e", "%5C", "\\", "@", "a"];
    let seed = 12345;
    const rand = () => {
      seed = (seed * 1664525 + 1013904223) % 4294967296;
      return seed / 4294967296;
    };
    for (let i = 0; i < 5000; i++) {
      const len = 1 + Math.floor(rand() * 8);
      let x = "";
      for (let j = 0; j < len; j++) x += pieces[Math.floor(rand() * pieces.length)];
      const once = safeCallbackPath(x, AUTH_URL);
      expect(safeCallbackPath(once, AUTH_URL), x).toBe(once);
      expect(once.startsWith("/"), x).toBe(true);
      expect(once.startsWith("//") || once.startsWith("/\\"), x).toBe(false);
    }
  });
});
