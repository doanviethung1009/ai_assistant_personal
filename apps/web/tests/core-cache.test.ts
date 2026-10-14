import { beforeEach, describe, expect, it } from "vitest";

import { cacheKey, cachedGet, coreCacheSize, invalidateCoreCache } from "@/lib/core-cache";

describe("core-cache: khoá bắt buộc có danh tính", () => {
  beforeEach(() => invalidateCoreCache());

  // T1
  it("khoá khác nhau theo uid và theo sv", () => {
    const p = "/api/v1/tasks?x=1";
    expect(cacheKey("A:1", p)).not.toBe(cacheKey("B:1", p));
    expect(cacheKey("A:1", p)).not.toBe(cacheKey("A:2", p));
    expect(cacheKey("A:1", p)).toBe(cacheKey("A:1", p));
  });

  it("identity rỗng ném lỗi và không thêm mục cache", () => {
    expect(() => cacheKey("", "/x")).toThrow();
    expect(() => cachedGet("", "/x", async () => 1)).toThrow();
    expect(coreCacheSize()).toBe(0);
  });

  // T3 (mức cache)
  it("cùng người, cùng path: loader chạy một lần", async () => {
    let calls = 0;
    const load = async () => ++calls;
    await cachedGet("A:1", "/p", load);
    await cachedGet("A:1", "/p", load);
    expect(calls).toBe(1);
  });

  it("người khác cùng path: loader chạy lại", async () => {
    let calls = 0;
    const load = async () => ++calls;
    await cachedGet("A:1", "/p", load);
    await cachedGet("B:1", "/p", load);
    expect(calls).toBe(2);
  });
});
