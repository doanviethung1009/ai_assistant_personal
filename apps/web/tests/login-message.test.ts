import { describe, expect, it } from "vitest";

import { GENERIC_FAILURE, loginErrorMessage } from "@/lib/login-message";

describe("loginErrorMessage", () => {
  it("không có error thì không có thông báo", () => {
    expect(loginErrorMessage(undefined, undefined)).toBeNull();
  });

  it("khoá prototype trên URL ra câu chung, không làm hỏng render", () => {
    for (const k of ["constructor", "toString", "__proto__", "hasOwnProperty"]) {
      expect(loginErrorMessage(k)).toBe(GENERIC_FAILURE);
    }
  });

  it("CredentialsSignin: code hợp lệ dùng code, code lạ/prototype rơi về invalid_credentials", () => {
    const base = loginErrorMessage("CredentialsSignin");
    expect(base).toContain("Sai thông tin đăng nhập");
    expect(loginErrorMessage("CredentialsSignin", "constructor")).toBe(base);
    expect(loginErrorMessage("CredentialsSignin", "zzz")).toBe(base);
    expect(loginErrorMessage("CredentialsSignin", "rate_limited")).toContain("quá nhiều lần");
  });

  it("mã đã biết và mã lạ", () => {
    expect(loginErrorMessage("not_invited")).toContain("chưa được cấp quyền");
    expect(loginErrorMessage("OAuthCallbackError")).toBe(GENERIC_FAILURE);
  });
});
