import { beforeEach, describe, expect, it, vi } from "vitest";

import { CoreApiError } from "@/lib/core-errors";

const UID = "11111111-1111-4111-8111-111111111111";
const TARGET = "22222222-2222-4222-8222-222222222222";

let session: { uid: string; sv: number } | null = { uid: UID, sv: 1 };
vi.mock("@/lib/session", () => ({ getSessionUser: async () => session }));

const permissions = vi.hoisted(() => ({ list: ["user:manage"] as string[] }));
const api = vi.hoisted(() => ({
  getMe: vi.fn(),
  createLocalUserApi: vi.fn(),
  deleteUserApi: vi.fn(),
  inviteGoogleUserApi: vi.fn(),
  resetUserPasswordApi: vi.fn(),
  revokeUserSessionsApi: vi.fn(),
  setUserAliasesApi: vi.fn(),
  unlockUserApi: vi.fn(),
  updateAdminUserApi: vi.fn(),
}));
vi.mock("@/lib/api", () => api);
const revalidatePath = vi.hoisted(() => vi.fn());
vi.mock("next/cache", () => ({ revalidatePath }));

function form(values: Record<string, string>): FormData {
  const f = new FormData();
  for (const [k, v] of Object.entries(values)) f.set(k, v);
  return f;
}

async function actions() {
  return await import("@/app/admin/actions");
}

describe("Server Action quản trị", () => {
  beforeEach(() => {
    vi.stubEnv("DATA_SOURCE", "api");
    session = { uid: UID, sv: 1 };
    permissions.list = ["user:manage"];
    for (const fn of Object.values(api)) fn.mockReset();
    api.getMe.mockImplementation(async () => ({ permissions: permissions.list }));
    revalidatePath.mockReset();
  });

  it("không phiên: mọi action trả unauthenticated và KHÔNG gọi core", async () => {
    const a = await actions();
    session = null;
    const results = [
      await a.inviteGoogleUserAction(form({ email: "x@y.z" })),
      await a.createLocalUserAction(form({ username: "abc", email: "x@y.z" })),
      await a.updateUserAction(TARGET, { role: "lead" }),
      await a.resetPasswordAction(TARGET),
      await a.unlockUserAction(TARGET),
      await a.revokeSessionsAction(TARGET),
      await a.deleteUserAction(TARGET),
      await a.setAliasesAction(TARGET, ["a"]),
    ];
    for (const r of results) expect(r).toMatchObject({ ok: false, code: "unauthenticated" });
    for (const [name, fn] of Object.entries(api)) if (name !== "getMe") expect(fn).not.toHaveBeenCalled();
  });

  it("thiếu user:manage (member/lead): forbidden, không gọi core", async () => {
    const a = await actions();
    permissions.list = ["task:read_work", "team:read"];
    expect(await a.deleteUserAction(TARGET)).toMatchObject({ ok: false, code: "forbidden" });
    expect(await a.resetPasswordAction(TARGET)).toMatchObject({ ok: false, code: "forbidden" });
    expect(api.deleteUserApi).not.toHaveBeenCalled();
    expect(api.resetUserPasswordApi).not.toHaveBeenCalled();
  });

  it("id không phải UUID bị từ chối trước khi gọi core (chống path injection)", async () => {
    const a = await actions();
    for (const id of ["../tasks", "abc", "", `${TARGET}/x`]) {
      expect(await a.deleteUserAction(id)).toMatchObject({ ok: false, code: "invalid" });
      expect(await a.unlockUserAction(id)).toMatchObject({ ok: false, code: "invalid" });
    }
    expect(api.deleteUserApi).not.toHaveBeenCalled();
    expect(api.unlockUserApi).not.toHaveBeenCalled();
  });

  it("tạo tài khoản nội bộ: trả mật khẩu tạm đúng một chỗ (kết quả action), không log, không revalidate kèm giá trị", async () => {
    const a = await actions();
    const spies = (["log", "error", "warn", "info", "debug"] as const).map((m) => vi.spyOn(console, m).mockImplementation(() => undefined));
    api.createLocalUserApi.mockResolvedValue({
      user: { username: "c.nguyen", email: "c@x.vn" },
      temporary_password: "Tmp-Secret-Pw-1234",
    });
    const result = await a.createLocalUserAction(form({ username: " C.Nguyen ", email: "C@X.vn", role: "member", name: "Cường" }));
    expect(result).toEqual({ ok: true, username: "c.nguyen", email: "c@x.vn", temporaryPassword: "Tmp-Secret-Pw-1234", aliasesSkipped: [] });
    expect(api.createLocalUserApi).toHaveBeenCalledWith({ username: "c.nguyen", email: "c@x.vn", role: "member", name: "Cường" });
    expect(revalidatePath).toHaveBeenCalledWith("/admin/users");
    expect(JSON.stringify(revalidatePath.mock.calls)).not.toContain("Tmp-Secret");
    for (const spy of spies) {
      expect(JSON.stringify(spy.mock.calls)).not.toContain("Tmp-Secret");
      spy.mockRestore();
    }
  });

  it("tạo tài khoản nội bộ: validate username/email/role/name", async () => {
    const a = await actions();
    const base = { username: "abc", email: "a@b.c", role: "member" };
    expect(await a.createLocalUserAction(form({ ...base, username: "a b" }))).toMatchObject({ ok: false, code: "invalid" });
    expect(await a.createLocalUserAction(form({ ...base, username: "ab" }))).toMatchObject({ ok: false });
    expect(await a.createLocalUserAction(form({ ...base, username: "a@b.c" }))).toMatchObject({ ok: false });
    expect(await a.createLocalUserAction(form({ ...base, email: "khong-co-a-cong" }))).toMatchObject({ ok: false });
    expect(await a.createLocalUserAction(form({ ...base, role: "root" }))).toMatchObject({ ok: false });
    expect(await a.createLocalUserAction(form({ ...base, name: "x".repeat(201) }))).toMatchObject({ ok: false });
    expect(api.createLocalUserApi).not.toHaveBeenCalled();
  });

  it("đặt lại mật khẩu trả mật khẩu tạm; lỗi core ánh xạ sang thông báo cố định", async () => {
    const a = await actions();
    api.resetUserPasswordApi.mockResolvedValueOnce({ temporary_password: "Reset-Pw-Value-9" });
    expect(await a.resetPasswordAction(TARGET)).toEqual({ ok: true, temporaryPassword: "Reset-Pw-Value-9" });
    api.resetUserPasswordApi.mockRejectedValueOnce(new CoreApiError("raw detail", 409, "self_action"));
    const failed = await a.resetPasswordAction(TARGET);
    expect(failed).toMatchObject({ ok: false, code: "self_action" });
    expect(JSON.stringify(failed)).not.toContain("raw detail");
  });

  it.each([
    ["self_lockout", 409],
    ["last_admin", 409],
    ["env_admin", 409],
    ["has_data", 409],
    ["email_exists", 409],
  ])("mã %s được trả về cho client kèm thông báo", async (code, status) => {
    const a = await actions();
    api.updateAdminUserApi.mockRejectedValue(new CoreApiError("x", status, code));
    expect(await a.updateUserAction(TARGET, { role: "member" })).toMatchObject({ ok: false, code });
  });

  it("phiên bị thu hồi giữa chừng → session_expired; password_change_required được nhận diện", async () => {
    const a = await actions();
    api.deleteUserApi.mockRejectedValueOnce(new CoreApiError("x", 401, "user_inactive"));
    expect(await a.deleteUserAction(TARGET)).toMatchObject({ ok: false, code: "session_expired" });
    api.deleteUserApi.mockRejectedValueOnce(new CoreApiError("x", 403, "password_change_required"));
    expect(await a.deleteUserAction(TARGET)).toMatchObject({ ok: false, code: "password_change_required" });
  });

  it("updateUserAction chỉ nhận trường trong danh sách cho phép", async () => {
    const a = await actions();
    const evil = { role: "member", is_env_admin: true } as unknown as Parameters<typeof a.updateUserAction>[1];
    expect(await a.updateUserAction(TARGET, evil)).toMatchObject({ ok: false, code: "invalid" });
    expect(await a.updateUserAction(TARGET, {})).toMatchObject({ ok: false, code: "invalid" });
    expect(await a.updateUserAction(TARGET, { status: "invited" as "active" })).toMatchObject({ ok: false });
    expect(api.updateAdminUserApi).not.toHaveBeenCalled();
    api.updateAdminUserApi.mockResolvedValue({});
    expect(await a.updateUserAction(TARGET, { role: "lead", status: "disabled" })).toEqual({ ok: true });
    expect(api.updateAdminUserApi).toHaveBeenCalledWith(TARGET, { role: "lead", status: "disabled" });
  });

  it("tạo local: gửi aliases đã chuẩn hoá, trả aliasesSkipped CÙNG mật khẩu tạm", async () => {
    const a = await actions();
    api.createLocalUserApi.mockResolvedValue({
      user: { username: "c.nguyen", email: "c@x.vn" },
      temporary_password: "Tmp-Secret-Pw-1234",
      aliases_skipped: ["Bình"],
    });
    const fd = form({ username: "c.nguyen", email: "c@x.vn", role: "member" });
    for (const v of [" An ", "An", "", "Bình"]) fd.append("aliases", v);
    const result = await a.createLocalUserAction(fd);
    expect(result).toMatchObject({ ok: true, temporaryPassword: "Tmp-Secret-Pw-1234", aliasesSkipped: ["Bình"] });
    expect(api.createLocalUserApi).toHaveBeenCalledWith({ username: "c.nguyen", email: "c@x.vn", role: "member", aliases: ["An", "Bình"] });
  });

  it("mời Google: gửi aliases, trả aliasesSkipped; alias sai bị chặn trước khi gọi core", async () => {
    const a = await actions();
    api.inviteGoogleUserApi.mockResolvedValue({ aliases_skipped: ["X", "Y"] });
    const fd = form({ email: "g@x.vn", role: "member" });
    fd.append("aliases", "X");
    expect(await a.inviteGoogleUserAction(fd)).toEqual({ ok: true, aliasesSkipped: ["X", "Y"] });
    expect(api.inviteGoogleUserApi).toHaveBeenCalledWith({ email: "g@x.vn", role: "member", aliases: ["X"] });

    api.inviteGoogleUserApi.mockClear();
    api.inviteGoogleUserApi.mockResolvedValue({});
    expect(await a.inviteGoogleUserAction(form({ email: "g@x.vn" }))).toEqual({ ok: true, aliasesSkipped: [] });
    expect(api.inviteGoogleUserApi).toHaveBeenCalledWith({ email: "g@x.vn", role: "member" });

    api.inviteGoogleUserApi.mockClear();
    for (const bad of ["a\nb", "x".repeat(201)]) {
      const f = form({ email: "g@x.vn" });
      f.append("aliases", bad);
      expect(await a.inviteGoogleUserAction(f)).toMatchObject({ ok: false, code: "invalid" });
    }
    const many = form({ email: "g@x.vn" });
    for (let i = 0; i < 21; i++) many.append("aliases", `n${i}`);
    expect(await a.inviteGoogleUserAction(many)).toMatchObject({ ok: false });
    expect(api.inviteGoogleUserApi).not.toHaveBeenCalled();
  });

  it("alias: cắt khoảng trắng, bỏ trùng/rỗng, từ chối ký tự điều khiển, > 20 và > 200 ký tự", async () => {
    const a = await actions();
    api.setUserAliasesApi.mockResolvedValue({});
    expect(await a.setAliasesAction(TARGET, [" An ", "An", "", "Bình"])).toEqual({ ok: true });
    expect(api.setUserAliasesApi).toHaveBeenCalledWith(TARGET, [
      { source: "jira", alias: "An" },
      { source: "jira", alias: "Bình" },
    ]);
    expect(await a.setAliasesAction(TARGET, ["a\nb"])).toMatchObject({ ok: false });
    expect(await a.setAliasesAction(TARGET, ["x".repeat(201)])).toMatchObject({ ok: false });
    expect(await a.setAliasesAction(TARGET, Array.from({ length: 21 }, (_, i) => `n${i}`))).toMatchObject({ ok: false });
    expect(await a.setAliasesAction(TARGET, "x" as unknown as string[])).toMatchObject({ ok: false });
  });
});
