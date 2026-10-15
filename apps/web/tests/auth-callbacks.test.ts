import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CoreApiError } from "@/lib/core-errors";
import { nextSessionToken } from "@/lib/session-token";

const corePasswordLogin = vi.fn();
const coreProbeMe = vi.fn();
vi.mock("@/lib/api", () => ({ corePasswordLogin, coreProbeMe }));

const UID = "11111111-1111-4111-8111-111111111111";
const EVIL = "22222222-2222-4222-8222-222222222222";

describe("callbacks.jwt (nextSessionToken)", () => {
  it("trigger update với uid/sv khác: token giữ nguyên uid, sv", () => {
    const token = { uid: UID, sv: 3 };
    const out = nextSessionToken({ token, trigger: "update", session: { uid: EVIL, sv: 99 } });
    expect(out).toEqual({ uid: UID, sv: 3 });
  });

  it("trigger update kèm user giả cũng bị bỏ qua", () => {
    const out = nextSessionToken({
      token: { uid: UID, sv: 3 },
      trigger: "update",
      user: { uid: EVIL, sv: 99 },
      session: { uid: EVIL, sv: 99 },
    });
    expect(out).toEqual({ uid: UID, sv: 3 });
  });

  it("đăng nhập: chép uid/sv từ user do signIn gắn", () => {
    expect(nextSessionToken({ token: {}, user: { uid: UID, sv: 7 } })).toEqual({ uid: UID, sv: 7 });
  });
});

describe("authorizePassword (Credentials.authorize)", () => {
  beforeEach(() => {
    corePasswordLogin.mockReset();
    coreProbeMe.mockReset();
    vi.unstubAllEnvs();
  });
  afterEach(() => vi.unstubAllEnvs());

  async function load() {
    return await import("@/lib/password-login");
  }

  async function codeOf(promise: Promise<unknown>): Promise<string | undefined> {
    try {
      await promise;
    } catch (error) {
      return (error as { code?: string }).code;
    }
    return undefined;
  }

  it("core 200 → { uid, sv }", async () => {
    const { authorizePassword } = await load();
    corePasswordLogin.mockResolvedValue({ user_id: UID, role: "member", session_version: 4 });
    const user = await authorizePassword({ identifier: "  c.nguyen ", password: "  pw with spaces  " }, null);
    expect(user).toEqual({ id: UID, uid: UID, sv: 4 });
    // identifier được trim, mật khẩu thì KHÔNG
    expect(corePasswordLogin).toHaveBeenCalledWith({
      identifier: "c.nguyen",
      password: "  pw with spaces  ",
      client_ip: null,
    });
  });

  it("core 403 invalid_credentials → CredentialsSignin có code=invalid_credentials", async () => {
    const { authorizePassword, PasswordLoginError } = await load();
    const { CredentialsSignin } = await import("next-auth");
    corePasswordLogin.mockRejectedValue(new CoreApiError("Sai thông tin", 403, "invalid_credentials"));
    const error = await authorizePassword({ identifier: "a", password: "b" }, null).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(CredentialsSignin);
    expect(error).toBeInstanceOf(PasswordLoginError);
    expect((error as { code: string }).code).toBe("invalid_credentials");
  });

  it.each([
    [new CoreApiError("x", 429), "rate_limited"],
    [new CoreApiError("x", 403, "password_login_disabled"), "password_login_disabled"],
    [new CoreApiError("x", 403), "unavailable"], // sai khoá API: cấu hình, không phải sai mật khẩu
    [new CoreApiError("x", 422), "invalid_credentials"],
    [new CoreApiError("x", 502), "unavailable"],
    [new Error("ECONNREFUSED"), "unavailable"],
  ])("lỗi core %# → %s", async (failure, code) => {
    const { authorizePassword } = await load();
    corePasswordLogin.mockRejectedValue(failure);
    expect(await codeOf(authorizePassword({ identifier: "a", password: "b" }, null))).toBe(code);
  });

  it("mật khẩu > 1024 ký tự hoặc sai kiểu → không gọi core", async () => {
    const { authorizePassword } = await load();
    expect(await codeOf(authorizePassword({ identifier: "a", password: "x".repeat(1025) }, null))).toBe("invalid_credentials");
    expect(await codeOf(authorizePassword({ identifier: "", password: "x" }, null))).toBe("invalid_credentials");
    expect(await codeOf(authorizePassword({ identifier: "a".repeat(321), password: "x" }, null))).toBe("invalid_credentials");
    expect(await codeOf(authorizePassword({ identifier: 5, password: "x" }, null))).toBe("invalid_credentials");
    expect(await codeOf(authorizePassword({ identifier: "a", password: ["x"] }, null))).toBe("invalid_credentials");
    expect(await codeOf(authorizePassword(undefined, null))).toBe("invalid_credentials");
    expect(corePasswordLogin).not.toHaveBeenCalled();
  });

  it("client_ip lấy hop tin cậy từ bên PHẢI, không phải hop đầu do client tự gửi", async () => {
    vi.stubEnv("TRUST_FORWARDED_FOR", "true");
    const { authorizePassword } = await load();
    corePasswordLogin.mockResolvedValue({ user_id: UID, role: "member", session_version: 1 });
    const headers = new Headers({ "x-forwarded-for": "6.6.6.6, 203.0.113.9" });
    await authorizePassword({ identifier: "a", password: "b" }, headers);
    expect(corePasswordLogin.mock.calls[0]?.[0].client_ip).toBe("203.0.113.9");
  });

  it("không tin X-Forwarded-For khi TRUST_FORWARDED_FOR chưa bật", async () => {
    const { authorizePassword } = await load();
    corePasswordLogin.mockResolvedValue({ user_id: UID, role: "member", session_version: 1 });
    await authorizePassword({ identifier: "a", password: "b" }, new Headers({ "x-forwarded-for": "6.6.6.6" }));
    expect(corePasswordLogin.mock.calls[0]?.[0].client_ip).toBeNull();
  });

  it("lỗi không chứa mật khẩu hay identifier", async () => {
    const { authorizePassword } = await load();
    corePasswordLogin.mockRejectedValue(new CoreApiError("boom", 403, "invalid_credentials"));
    const error = (await authorizePassword({ identifier: "secret-id", password: "secret-pw" }, null).catch((e: unknown) => e)) as Error;
    expect(JSON.stringify({ m: error.message, c: (error as { code?: string }).code })).not.toMatch(/secret-(id|pw)/);
  });
});

describe("verifySessionWithCore (signIn bước 4)", () => {
  beforeEach(() => coreProbeMe.mockReset());

  it("ok → true", async () => {
    const { verifySessionWithCore } = await import("@/lib/password-login");
    coreProbeMe.mockResolvedValue({});
    expect(await verifySessionWithCore(UID, 1)).toBe(true);
  });

  it("401 token_invalid → /login?error=config; lỗi khác → unavailable", async () => {
    const { verifySessionWithCore } = await import("@/lib/password-login");
    coreProbeMe.mockRejectedValueOnce(new CoreApiError("x", 401, "token_invalid"));
    expect(await verifySessionWithCore(UID, 1)).toBe("/login?error=config");
    coreProbeMe.mockRejectedValueOnce(new Error("down"));
    expect(await verifySessionWithCore(UID, 1)).toBe("/login?error=unavailable");
  });
});
