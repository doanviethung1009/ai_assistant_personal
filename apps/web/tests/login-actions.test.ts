import { isRedirectError } from "next/dist/client/components/redirect-error";
import { redirect } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";

const signIn = vi.fn();
vi.mock("@/auth", () => ({ signIn, signOut: vi.fn() }));

let config: { ok: true; authUrl: string; passwordEnabled: boolean; googleEnabled: boolean } = {
  ok: true,
  authUrl: "http://localhost:3000",
  passwordEnabled: true,
  googleEnabled: true,
};
vi.mock("@/lib/auth-config", () => ({
  authEnabled: () => true,
  readAuthConfig: () => config,
}));

function form(values: Record<string, string>): FormData {
  const f = new FormData();
  for (const [k, v] of Object.entries(values)) f.set(k, v);
  return f;
}

describe("passwordSignInAction", () => {
  beforeEach(() => {
    signIn.mockReset();
    config = { ok: true, authUrl: "http://localhost:3000", passwordEnabled: true, googleEnabled: true };
  });

  it("lỗi redirect của Next được ném lại (đăng nhập thành công phải chuyển trang)", async () => {
    const { passwordSignInAction } = await import("@/app/login/actions");
    signIn.mockImplementation(async () => redirect("/tasks"));
    const error = await passwordSignInAction({}, form({ identifier: "a", password: "b" })).catch((e: unknown) => e);
    expect(isRedirectError(error)).toBe(true);
  });

  it("CredentialsSignin → { error } với mã cố định, giữ identifier, không chứa mật khẩu", async () => {
    const { passwordSignInAction } = await import("@/app/login/actions");
    const { PasswordLoginError } = await import("@/lib/password-login");
    signIn.mockRejectedValue(new PasswordLoginError("invalid_credentials"));
    const state = await passwordSignInAction({}, form({ identifier: "c.nguyen", password: "hunter2-hunter2" }));
    expect(state).toEqual({ error: "invalid_credentials", identifier: "c.nguyen" });
    expect(JSON.stringify(state)).not.toContain("hunter2");
  });

  it("mã rate_limited đi qua; AuthError khác → unavailable", async () => {
    const { passwordSignInAction } = await import("@/app/login/actions");
    const { PasswordLoginError } = await import("@/lib/password-login");
    const { AuthError } = await import("next-auth");
    signIn.mockRejectedValueOnce(new PasswordLoginError("rate_limited"));
    expect((await passwordSignInAction({}, form({ identifier: "a", password: "b" }))).error).toBe("rate_limited");
    signIn.mockRejectedValueOnce(new AuthError("boom"));
    expect((await passwordSignInAction({}, form({ identifier: "a", password: "b" }))).error).toBe("unavailable");
  });

  it("lỗi không phải AuthError thì ném lại (không nuốt)", async () => {
    const { passwordSignInAction } = await import("@/app/login/actions");
    signIn.mockRejectedValue(new TypeError("bug"));
    await expect(passwordSignInAction({}, form({ identifier: "a", password: "b" }))).rejects.toThrow("bug");
  });

  it("mật khẩu > 1024 ký tự hoặc rỗng: không gọi signIn", async () => {
    const { passwordSignInAction } = await import("@/app/login/actions");
    expect((await passwordSignInAction({}, form({ identifier: "a", password: "x".repeat(1025) }))).error).toBe("invalid_credentials");
    expect((await passwordSignInAction({}, form({ identifier: "a", password: "" }))).error).toBe("invalid_credentials");
    expect((await passwordSignInAction({}, form({ identifier: "  ", password: "x" }))).error).toBe("invalid_credentials");
    expect(signIn).not.toHaveBeenCalled();
  });

  it("PASSWORD_LOGIN_ENABLED=false: không gọi signIn", async () => {
    const { passwordSignInAction } = await import("@/app/login/actions");
    config = { ...config, passwordEnabled: false };
    expect((await passwordSignInAction({}, form({ identifier: "a", password: "b" }))).error).toBe("password_login_disabled");
    expect(signIn).not.toHaveBeenCalled();
  });

  it("callbackUrl ngoài origin bị lọc về /", async () => {
    const { passwordSignInAction } = await import("@/app/login/actions");
    signIn.mockResolvedValue(undefined);
    await passwordSignInAction({}, form({ identifier: "a", password: "b", callbackUrl: "https://evil.example/x" }));
    expect(signIn).toHaveBeenCalledWith("credentials", { identifier: "a", password: "b", redirectTo: "/" });
    signIn.mockClear();
    await passwordSignInAction({}, form({ identifier: "a", password: "b", callbackUrl: "/tasks?x=1" }));
    expect(signIn.mock.calls[0]?.[1].redirectTo).toBe("/tasks?x=1");
  });
});
