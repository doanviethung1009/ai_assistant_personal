import { describe, expect, it } from "vitest";

import { normalizeAliases, skippedAliasesMessage } from "@/lib/alias-input";
import { buildPeopleJql } from "@/lib/jira-jql";
import { parseCsv, tasksToCsv } from "@/lib/store/csv";
import {
  checkJqlLength,
  cleanName,
  cleanReporter,
  neutralizeCsvCell,
  restoreCsvCell,
} from "@/lib/text-safety";

describe("CSV formula injection", () => {
  it.each(["=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx"])("vô hiệu %j", (v) => {
    expect(neutralizeCsvCell(v)).toBe(`'${v}`);
  });
  it("giữ nguyên ô bình thường và gỡ lại được", () => {
    expect(neutralizeCsvCell("abc")).toBe("abc");
    expect(restoreCsvCell("'=1+1")).toBe("=1+1");
    expect(restoreCsvCell("'abc")).toBe("'abc");
  });
  it("export CSV task có tiền tố và import lại ra đúng giá trị", () => {
    const task = {
      id: "00000000-0000-0000-0000-000000000001",
      title: "=HYPERLINK(\"http://x\")",
      status: "todo",
      priority: "medium",
      source: "manual",
      tags: [],
      events: [],
      spent_minutes: 0,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    } as never;
    const csv = tasksToCsv([task], []);
    expect(csv).toContain("'=HYPERLINK");
    const rows = parseCsv(csv);
    expect(rows.flat()).toContain('=HYPERLINK("http://x")');
  });
});

describe("tên toàn khoảng trắng", () => {
  it("NBSP, zero-width, ZWJ coi là rỗng", () => {
    for (const v of ["", "   ", " ", "​", "‍‌", "  ​ "]) expect(cleanName(v)).toBe("");
    expect(cleanName(" An ")).toBe("An");
  });
  it("normalizeAliases bỏ mục rỗng kiểu NBSP/zero-width", () => {
    expect(normalizeAliases([" ", "​", "An"])).toEqual({ ok: true, aliases: ["An"] });
  });
  it("câu cảnh báo theo động từ", () => {
    expect(skippedAliasesMessage(["X"], "được mời")).toContain("đã được mời");
  });
});

describe("giới hạn JQL", () => {
  it("quá 4000 ký tự thì báo 'JQL quá dài'", () => {
    expect(checkJqlLength("a".repeat(4000))).toBeNull();
    expect(checkJqlLength("a".repeat(4001))).toBe("JQL quá dài");
    expect(checkJqlLength(buildPeopleJql("", ["x".repeat(100), ...Array(60).fill("y".repeat(90))], []))).toBe("JQL quá dài");
  });
});

describe("tên reporter", () => {
  it("bỏ ký tự điều khiển/bidi, cắt 200, rỗng thì null", () => {
    expect(cleanReporter("  An\u0000‮ B\n ")).toBe("An B");
    expect(cleanReporter("​ ")).toBeNull();
    expect(cleanReporter("x".repeat(300))?.length).toBe(200);
    expect(cleanReporter(42)).toBeNull();
  });
});
