import { isRedirectError } from "next/dist/client/components/redirect-error";
import { redirect } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CoreApiError } from "@/lib/core-errors";

const UID = "11111111-1111-4111-8111-111111111111";
const signIn = vi.hoisted(() => vi.fn());
vi.mock("@/auth", () => ({ signIn, signOut: vi.fn() }));
vi.mock("@/lib/session", () => ({ getSessionUser: async () => ({ uid: UID, sv: 1 }) }));
const api = vi.hoisted(() => ({ getMe: vi.fn(), changeMyPasswordApi: vi.fn() }));
vi.mock("@/lib/api", () => api);

const CURRENT = "mat-khau-cu-12345";
const NEXT = "mat-khau-moi-67890";

function form(over: Record<string, string> = {}): FormData {
  const f = new FormData();
  const v = { current_password: CURRENT, new_password: NEXT, confirm_password: NEXT, ...over };
  for (const [k, val] of Object.entries(v)) f.set(k, val);
  return f;
}

function coreError(status: number, code: string, message: string): CoreApiError {
  return new CoreApiError(message, status, code);
}

async function run(data = form()) {
  const { changeMyPasswordAction } = await import("@/app/me/actions");
  return changeMyPasswordAction({}, data);
}

describe("changeMyPasswordAction", () => {
  beforeEach(() => {
    vi.stubEnv("DATA_SOURCE", "api");
    signIn.mockReset();
    api.getMe.mockReset().mockResolvedValue({ auth_provider: "local", username: "c.nguyen" });
    api.changeMyPasswordApi.mockReset().mockResolvedValue(undefined);
  });

  it("đổi xong thì đăng nhập lại bằng mật khẩu mới và ném lại redirect", async () => {
    signIn.mockImplementation(async () => redirect("/"));
    const error = await run().catch((e: unknown) => e);
    expect(isRedirectError(error)).toBe(true);
    expect(signIn).toHaveBeenCalledWith("credentials", { identifier: "c.nguyen", password: NEXT, redirectTo: "/" });
  });

  it("signIn lỗi thường sau khi đã đổi → relogin_required, không chứa mật khẩu", async () => {
    signIn.mockRejectedValue(new Error("boom"));
    const state = await run();
    expect(state).toEqual({ ok: true, code: "relogin_required" });
  });

  it("current_password_invalid", async () => {
    api.changeMyPasswordApi.mockRejectedValue(coreError(400, "current_password_invalid", "sai"));
    const state = await run();
    expect(state).toMatchObject({ ok: false, code: "current_password_invalid" });
    expect(JSON.stringify(state)).not.toContain(CURRENT);
    expect(JSON.stringify(state)).not.toContain(NEXT);
  });

  it("weak_password: reasons bỏ tiêu đề lặp, state không chứa mật khẩu", async () => {
    api.changeMyPasswordApi.mockRejectedValue(
      coreError(422, "weak_password", "Mật khẩu mới không đạt: quá ngắn; nằm trong danh sách phổ biến"),
    );
    const state = await run();
    expect(state).toMatchObject({ ok: false, code: "weak_password", reasons: ["quá ngắn", "nằm trong danh sách phổ biến"] });
    expect(JSON.stringify(state)).not.toContain(NEXT);
  });

  it("429 → rate_limited", async () => {
    api.changeMyPasswordApi.mockRejectedValue(coreError(429, "too_many", "x"));
    expect(await run()).toMatchObject({ ok: false, code: "rate_limited" });
  });

  it("xác nhận không khớp thì không gọi core", async () => {
    const state = await run(form({ confirm_password: "khac" }));
    expect(state).toMatchObject({ ok: false, code: "mismatch" });
    expect(api.changeMyPasswordApi).not.toHaveBeenCalled();
  });
});
