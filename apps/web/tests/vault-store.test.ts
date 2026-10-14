import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { vaultFilePath } from "@/lib/vault/store";

const UID = "11111111-1111-4111-8111-111111111111";

describe("vaultFilePath", () => {
  beforeEach(() => vi.stubEnv("DATA_DIR", "/data"));
  afterEach(() => vi.unstubAllEnvs());

  it("null (local) → vault.json", () => {
    expect(vaultFilePath(null)).toBe(path.join("/data", "vault.json"));
  });

  it("UUID → vault-<uid>.json (chữ thường)", () => {
    expect(vaultFilePath(UID)).toBe(path.join("/data", `vault-${UID}.json`));
    expect(vaultFilePath(UID.toUpperCase())).toBe(path.join("/data", `vault-${UID}.json`));
  });

  it.each(["../x", "..", "a/b", "", `${UID}/../x`, "local", `${UID}\n`])("từ chối %j", (owner) => {
    expect(() => vaultFilePath(owner)).toThrow();
  });
});
