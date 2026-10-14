import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const APP_DIR = path.resolve(__dirname, "..", "app");

/** Miễn trừ: chỉ file chưa có phiên là đúng (đăng nhập). Thêm miễn trừ phải kèm lý do ở đây. */
const EXEMPT = new Set([path.join("login", "actions.ts")]);

const GUARD_RE = /^\s*const \w+ = await require(Session|Permission)\(/;
/** Dòng kế tiếp phải trả ngay khi guard thất bại. */
const RETURN_RE = /^\s*if \(!\w+\.ok\) return/;

/**
 * Mọi export KHÁC `export async function` (và `export interface/type`, bị xoá lúc biên dịch) đều
 * bị cấm trong file "use server": `export const x = async`, `export default async function`,
 * `export { ... }`... là cách lách bộ quét hàm, hoặc là export không phải action.
 */
const ALLOWED_EXPORT_RE = /^export (async function \w+|interface \w+|type \w+)/;

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return walk(full);
    return full.endsWith(".ts") ? [full] : [];
  });
}

function netDepth(line: string): number {
  const noArrow = line.replace(/=>/g, "");
  const count = (re: RegExp) => (noArrow.match(re) ?? []).length;
  return count(/\(/g) - count(/\)/g) + count(/</g) - count(/>/g);
}

/** Với mỗi `export async function`, trả câu lệnh đầu tiên của thân hàm. */
function firstStatements(source: string): { name: string; first: string; second: string }[] {
  const lines = source.split("\n");
  const found: { name: string; first: string; second: string }[] = [];
  for (let i = 0; i < lines.length; i++) {
    const m = /^export async function (\w+)/.exec(lines[i] ?? "");
    if (!m) continue;
    let depth = 0;
    let j = i;
    for (; j < lines.length; j++) {
      depth += netDepth(lines[j] ?? "");
      if (depth <= 0 && (lines[j] ?? "").trimEnd().endsWith("{")) break;
    }
    let k = j + 1;
    while (k < lines.length && (lines[k] ?? "").trim() === "") k++;
    let n = k + 1;
    while (n < lines.length && (lines[n] ?? "").trim() === "") n++;
    found.push({ name: m[1] ?? "?", first: lines[k] ?? "", second: lines[n] ?? "" });
  }
  return found;
}

describe("Server Action phải mở đầu bằng guard phiên/quyền", () => {
  const files = walk(APP_DIR).filter((f) => /^\s*["']use server["']/.test(readFileSync(f, "utf8")));

  it("tìm thấy các file action", () => {
    expect(files.length).toBeGreaterThanOrEqual(6);
  });

  for (const file of files) {
    const rel = path.relative(APP_DIR, file);
    if (EXEMPT.has(rel)) continue;
    it(rel, () => {
      const actions = firstStatements(readFileSync(file, "utf8"));
      expect(actions.length).toBeGreaterThan(0);
      const missing = actions.filter((a) => !GUARD_RE.test(a.first)).map((a) => a.name);
      expect(missing).toEqual([]);
      const noReturn = actions.filter((a) => !RETURN_RE.test(a.second)).map((a) => a.name);
      expect(noReturn).toEqual([]);
    });

    it(`${rel}: chỉ export async function (hoặc interface/type)`, () => {
      const offenders = readFileSync(file, "utf8")
        .split("\n")
        .filter((line) => line.startsWith("export ") && !ALLOWED_EXPORT_RE.test(line));
      expect(offenders).toEqual([]);
    });
  }

  it("bộ bắt lỗi thật sự đỏ khi thiếu guard", () => {
    const bad = 'export async function evil(id: string): Promise<{ ok: boolean }> {\n  doStuff();\n  return { ok: true };\n}';
    expect(firstStatements(bad).every((a) => GUARD_RE.test(a.first))).toBe(false);
  });

  it("bộ bắt lỗi đỏ khi có guard nhưng quên return, hoặc export lách", () => {
    const noReturn = 'export async function a(): Promise<void> {\n  const auth = await requireSession();\n  doStuff();\n}';
    expect(firstStatements(noReturn).every((a) => RETURN_RE.test(a.second))).toBe(false);
    for (const line of ["export const x = async () => {};", "export default async function f() {", "export { a, b };", "export function sync() {"]) {
      expect(ALLOWED_EXPORT_RE.test(line)).toBe(false);
    }
  });
});
