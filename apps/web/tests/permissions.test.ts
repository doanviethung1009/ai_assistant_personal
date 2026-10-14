import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { PERMISSIONS, hasPermission } from "@/lib/permissions";

describe("lib/permissions khớp core/permissions.py", () => {
  const py = readFileSync(
    path.resolve(__dirname, "..", "..", "core", "app", "core", "permissions.py"),
    "utf8",
  );
  const fromCore = [...py.matchAll(/= "([a-z_]+:[a-z_]+)"/g)].map((m) => m[1]).sort();

  it("đúng 9 giá trị, trùng nhau", () => {
    expect(fromCore).toHaveLength(9);
    expect([...PERMISSIONS].sort()).toEqual(fromCore);
  });

  it("hasPermission", () => {
    expect(hasPermission("all", "system:read")).toBe(true);
    expect(hasPermission(["team:read"], "team:read")).toBe(true);
    expect(hasPermission(["team:read"], "system:read")).toBe(false);
    expect(hasPermission([], "team:read")).toBe(false);
  });
});
