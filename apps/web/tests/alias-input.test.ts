import { describe, expect, it } from "vitest";

import { cleanSkippedAliases, normalizeAliases, skippedAliasesMessage, splitAliasText } from "@/lib/alias-input";

describe("alias-input", () => {
  it("tách theo dấu phẩy và xuống dòng", () => {
    expect(splitAliasText("a, b\nc")).toEqual(["a", " b", "c"]);
  });

  it("chuẩn hoá: trim, bỏ rỗng, bỏ trùng giữ thứ tự", () => {
    expect(normalizeAliases([" An ", "An", "", "Bình", "  "])).toEqual({ ok: true, aliases: ["An", "Bình"] });
  });

  it("từ chối ký tự điều khiển, > 200 ký tự, > 20 mục, kiểu sai", () => {
    expect(normalizeAliases(["a\tb"]).ok).toBe(false);
    expect(normalizeAliases(["x".repeat(201)]).ok).toBe(false);
    expect(normalizeAliases(["x".repeat(200)]).ok).toBe(true);
    expect(normalizeAliases(Array.from({ length: 21 }, (_, i) => `n${i}`)).ok).toBe(false);
    expect(normalizeAliases(Array.from({ length: 20 }, (_, i) => `n${i}`)).ok).toBe(true);
    expect(normalizeAliases("x").ok).toBe(false);
    expect(normalizeAliases([1]).ok).toBe(false);
  });

  it("aliases_skipped: lọc rác, thiếu field thì rỗng", () => {
    expect(cleanSkippedAliases(undefined)).toEqual([]);
    expect(cleanSkippedAliases("x")).toEqual([]);
    expect(cleanSkippedAliases(["A", 3, " ", "B"])).toEqual(["A", "B"]);
  });

  it("thông báo nêu đủ tên và nói rõ user đã được tạo", () => {
    const msg = skippedAliasesMessage(["X", "Y"]);
    expect(msg).toContain('"X", "Y"');
    expect(msg).toContain("đã được tạo");
  });
});
