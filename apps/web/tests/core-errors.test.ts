import { describe, expect, it } from "vitest";

import { classifyCoreError, CoreApiError } from "@/lib/core-errors";

describe("classifyCoreError (bảng 3.4)", () => {
  it.each([
    [new CoreApiError("x", 401, "no_session"), "unauthenticated"],
    [new CoreApiError("x", 401, "token_invalid"), "session_expired"],
    [new CoreApiError("x", 401, "user_inactive"), "session_expired"],
    [new CoreApiError("x", 401), "config"],
    [new CoreApiError("x", 403, "forbidden"), "forbidden"],
    [new CoreApiError("x", 403), "config"],
    [new CoreApiError("x", 404), "other"],
    [new CoreApiError("x", 502), "other"],
    [new Error("ECONNREFUSED"), "other"],
  ])("%#", (error, kind) => {
    expect(classifyCoreError(error)).toBe(kind);
  });
});
