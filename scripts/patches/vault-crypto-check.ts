// Kiểm thử vòng đời mã hoá Két. Chạy: npx tsx scripts/patches/vault-crypto-check.ts
import {
  createVault,
  encryptPayload,
  regenerateRecovery,
  rewrapPassword,
  unlockBlob,
  unlockWithRecovery,
  isVaultBlob,
  WrongPasswordError,
} from "../../apps/web/lib/vault/crypto";

function assert(cond: boolean, msg: string) {
  if (!cond) throw new Error("FAIL: " + msg);
  console.log("ok  -", msg);
}

const payload = {
  entries: [
    { id: "1", name: "pg", system_type: "database", project: "", tags: [], fields: [], notes: "x", created_at: "", updated_at: "" },
  ],
};

async function rejects(p: Promise<unknown>): Promise<boolean> {
  try { await p; return false; } catch (e) { return e instanceof WrongPasswordError; }
}

(async () => {
  const { session, recoveryKey } = await createVault("correct horse battery");
  const blob = JSON.parse(JSON.stringify(await encryptPayload(session, payload)));
  assert(isVaultBlob(blob), "blob v2 hợp lệ");
  assert(/^([A-Z2-9]{4}-){7}[A-Z2-9]{4}$/.test(recoveryKey), "định dạng mã khôi phục");

  const a = await unlockBlob("correct horse battery", blob);
  assert(a.payload.entries[0]?.name === "pg", "mở bằng mật khẩu");
  assert(await rejects(unlockBlob("wrong password!!", blob)), "sai mật khẩu bị từ chối");

  const b = await unlockWithRecovery(recoveryKey.toLowerCase().replace(/-/g, " "), "new password 12345", blob);
  assert(b.payload.entries[0]?.name === "pg", "mở bằng mã khôi phục (nhập thường, bỏ gạch)");
  const blob2 = JSON.parse(JSON.stringify(await encryptPayload(b.session, b.payload)));
  assert((await unlockBlob("new password 12345", blob2)).payload.entries.length === 1, "mật khẩu mới hoạt động");
  assert(await rejects(unlockBlob("correct horse battery", blob2)), "mật khẩu cũ hết hiệu lực");
  assert((await unlockWithRecovery(recoveryKey, "another one 12345", blob2)).payload.entries.length === 1, "mã khôi phục vẫn dùng được sau khi đổi mật khẩu");

  const re = await regenerateRecovery(b.session);
  const blob3 = JSON.parse(JSON.stringify(await encryptPayload(re.session, b.payload)));
  assert(await rejects(unlockWithRecovery(recoveryKey, "zzzzzzzzzzzz", blob3)), "mã khôi phục cũ mất hiệu lực");
  assert((await unlockWithRecovery(re.recoveryKey, "zzzzzzzzzzzz", blob3)).payload.entries.length === 1, "mã mới hoạt động");

  const rw = await rewrapPassword(b.session, "rewrapped pw 123");
  const blob4 = JSON.parse(JSON.stringify(await encryptPayload(rw, b.payload)));
  assert((await unlockBlob("rewrapped pw 123", blob4)).payload.entries.length === 1, "đổi mật khẩu bằng rewrap");

  const tampered = { ...blob, ciphertext: blob.ciphertext.slice(0, -4) + "AAAA" };
  assert(await rejects(unlockBlob("correct horse battery", tampered)), "blob bị sửa bị từ chối");
  console.log("TẤT CẢ ĐẠT");
})().catch((e) => { console.error(e); process.exit(1); });
