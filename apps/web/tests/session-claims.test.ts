import { describe, expect, it } from "vitest";

import { parseSessionClaims } from "@/lib/session-claims";

const UID = "11111111-1111-4111-8111-111111111111";

describe("parseSessionClaims (dùng chung middleware và getSessionUser)", () => {
  it("uid UUID + sv nguyên >= 0 là phiên hợp lệ", () => {
    expect(parseSessionClaims({ uid: UID, sv: 0 })).toEqual({ uid: UID, sv: 0 });
  });

  // Middleware dùng đúng hàm này để quyết định hasSession: null → coi như chưa đăng nhập, nên
  // /login không chuyển về "/" (hết vòng lặp /login <-> "/").
  it.each([
    [{ uid: UID }],
    [{ uid: UID, sv: -1 }],
    [{ uid: UID, sv: 1.5 }],
    [{ uid: UID, sv: "1" }],
    [{ uid: "not-a-uuid", sv: 1 }],
    [{ uid: "", sv: 1 }],
    [{ sv: 1 }],
    [null],
    [undefined],
  ])("%j → null (chưa đăng nhập)", (raw) => {
    expect(parseSessionClaims(raw)).toBeNull();
  });
});
