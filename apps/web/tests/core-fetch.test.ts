import { decodeJwt, jwtVerify } from "jose";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const SECRET = "x".repeat(40);
const UID_A = "11111111-1111-4111-8111-111111111111";
const UID_B = "22222222-2222-4222-8222-222222222222";

let current: { uid: string; sv: number } | null = null;
vi.mock("@/lib/session", () => ({ getSessionUser: async () => current }));

const fetchMock = vi.fn();

/** Mock core: body trả về theo `sub` trong Bearer để bắt rò chéo người dùng. */
function coreResponder(_url: string, init: RequestInit): Response {
  const auth = new Headers(init.headers).get("Authorization") ?? "";
  const sub = auth.startsWith("Bearer ") ? decodeJwt(auth.slice(7)).sub : "anon";
  return new Response(JSON.stringify({ owner: sub }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

async function load() {
  vi.resetModules();
  vi.stubEnv("DATA_SOURCE", "api");
  vi.stubEnv("CORE_API_KEY", "test-key");
  vi.stubEnv("CORE_API_URL", "http://core.test");
  vi.stubEnv("CORE_JWT_SECRET", SECRET);
  const api = await import("@/lib/api");
  const cache = await import("@/lib/core-cache");
  cache.invalidateCoreCache();
  return { api, cache };
}

describe("coreFetch (api mode)", () => {
  beforeEach(() => {
    current = null;
    fetchMock.mockReset();
    fetchMock.mockImplementation(async (url: string, init: RequestInit) => coreResponder(url, init));
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  // T2
  it("A rồi B GET cùng path trong TTL: fetch 2 lần, B nhận body của B", async () => {
    const { api } = await load();
    current = { uid: UID_A, sv: 1 };
    const a = await api.coreFetch<{ owner: string }>("/api/v1/tasks");
    current = { uid: UID_B, sv: 1 };
    const b = await api.coreFetch<{ owner: string }>("/api/v1/tasks");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(a.owner).toBe(UID_A);
    expect(b.owner).toBe(UID_B);
  });

  // T3
  it("cùng người, cùng path trong TTL: fetch 1 lần", async () => {
    const { api } = await load();
    current = { uid: UID_A, sv: 1 };
    await api.coreFetch("/api/v1/tasks");
    await api.coreFetch("/api/v1/tasks");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("đổi sv (thu hồi phiên) ra khoá mới", async () => {
    const { api } = await load();
    current = { uid: UID_A, sv: 1 };
    await api.coreFetch("/api/v1/tasks");
    current = { uid: UID_A, sv: 2 };
    await api.coreFetch("/api/v1/tasks");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  // T4
  it("A ghi (POST) rồi B GET: gọi lại fetch", async () => {
    const { api } = await load();
    current = { uid: UID_B, sv: 1 };
    await api.coreFetch("/api/v1/tasks");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    current = { uid: UID_A, sv: 1 };
    await api.coreFetch("/api/v1/tasks", { method: "POST", body: "{}" });
    current = { uid: UID_B, sv: 1 };
    await api.coreFetch("/api/v1/tasks");
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  // T5
  it("/api/v1/me hai lần cùng người: fetch 2 lần (không cache dùng chung)", async () => {
    const { api } = await load();
    current = { uid: UID_A, sv: 1 };
    await api.coreFetch("/api/v1/me");
    await api.coreFetch("/api/v1/me");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("/api/v1/members không bị nhầm với /api/v1/me (vẫn cache)", async () => {
    const { api } = await load();
    current = { uid: UID_A, sv: 1 };
    await api.coreFetch("/api/v1/members");
    await api.coreFetch("/api/v1/members");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  // T6
  it("không phiên: ném 401 no_session, không gọi fetch, cache không thêm mục", async () => {
    const { api, cache } = await load();
    current = null;
    await expect(api.coreFetch("/api/v1/tasks")).rejects.toMatchObject({ status: 401, code: "no_session" });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(cache.coreCacheSize()).toBe(0);
  });

  // T7
  it("Authorization do caller truyền bị ghi đè bằng token của phiên", async () => {
    const { api } = await load();
    current = { uid: UID_A, sv: 1 };
    const res = await api.coreFetch<{ owner: string }>("/api/v1/me", {
      headers: { Authorization: "Bearer attacker" },
    });
    expect(res.owner).toBe(UID_A);
    const sent = new Headers((fetchMock.mock.calls[0]?.[1] as RequestInit).headers);
    const bearer = sent.get("Authorization") ?? "";
    expect(bearer).toMatch(/^Bearer /);
    expect(bearer).not.toContain("attacker");
    expect(decodeJwt(bearer.slice(7)).sub).toBe(UID_A);
    expect(sent.get("X-API-Key")).toBe("test-key");
  });

  it("coreLogin không gửi Bearer (chưa có phiên) nhưng vẫn có X-API-Key", async () => {
    const { api } = await load();
    await api.coreLogin(
      { google_sub: "s", email: "a@b.c", email_verified: true },
      null,
    );
    const sent = new Headers((fetchMock.mock.calls[0]?.[1] as RequestInit).headers);
    expect(sent.get("Authorization")).toBeNull();
    expect(sent.get("X-API-Key")).toBe("test-key");
  });

  it("code trong body lỗi được đưa vào CoreApiError", async () => {
    const { api } = await load();
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "x", code: "user_inactive" }), { status: 401 }),
    );
    current = { uid: UID_A, sv: 1 };
    await expect(api.coreFetch("/api/v1/tasks")).rejects.toMatchObject({ status: 401, code: "user_inactive" });
  });
});

// T8
describe("signCoreToken", () => {
  it("verify được bằng jose cùng secret, đúng claim, exp-iat = 60, có jti", async () => {
    const { signCoreToken } = await import("@/lib/core-jwt");
    const token = await signCoreToken({ uid: UID_A, sv: 3 }, SECRET);
    const { payload, protectedHeader } = await jwtVerify(token, new TextEncoder().encode(SECRET), {
      issuer: "builder-web",
      audience: "builder-core",
    });
    expect(protectedHeader.alg).toBe("HS256");
    expect(payload.sub).toBe(UID_A);
    expect(payload.sv).toBe(3);
    expect(payload.exp! - payload.iat!).toBe(60);
    expect(typeof payload.jti).toBe("string");
    expect(Object.keys(payload).sort()).toEqual(["aud", "exp", "iat", "iss", "jti", "sub", "sv"]);
  });

  it("jti khác nhau mỗi lần ký", async () => {
    const { signCoreToken } = await import("@/lib/core-jwt");
    const a = decodeJwt(await signCoreToken({ uid: UID_A, sv: 0 }, SECRET));
    const b = decodeJwt(await signCoreToken({ uid: UID_A, sv: 0 }, SECRET));
    expect(a.jti).not.toBe(b.jti);
  });

  it("secret ngắn hơn 32 ký tự ném lỗi cấu hình", async () => {
    const { signCoreToken } = await import("@/lib/core-jwt");
    await expect(signCoreToken({ uid: UID_A, sv: 0 }, "short")).rejects.toThrow(/CORE_JWT_SECRET/);
    await expect(signCoreToken({ uid: UID_A, sv: 0 }, undefined)).rejects.toThrow(/CORE_JWT_SECRET/);
  });
});
