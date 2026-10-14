import { describe, expect, it } from "vitest";

import { nextSessionToken } from "@/lib/session-token";

describe("nextSessionToken (callbacks.jwt)", () => {
  const token = { uid: "11111111-1111-4111-8111-111111111111", sv: 1 };

  it("đăng nhập: chép uid/sv từ user", () => {
    expect(nextSessionToken({ token: {}, user: { uid: "u", sv: 4 } })).toEqual({ uid: "u", sv: 4 });
  });

  it("trigger update với dữ liệu client gửi: bỏ qua, giữ uid/sv cũ", () => {
    const evil = { uid: "22222222-2222-4222-8222-222222222222", sv: 99 };
    expect(nextSessionToken({ token, trigger: "update", session: evil })).toEqual(token);
    expect(nextSessionToken({ token, trigger: "update", session: evil, user: evil })).toEqual(token);
  });

  it("request thường: giữ nguyên, không thêm field nào khác", () => {
    expect(nextSessionToken({ token: { ...token, role: "admin" } as typeof token })).toEqual(token);
  });
});
