import "server-only";

import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

import { defaultScopeFor, parseScope } from "../task-scope";
import * as engine from "./engine";
import { SCHEMA_VERSION, type DataFile } from "./types";

/**
 * Lưu dữ liệu xuống một file JSON.
 *
 * Ba điều đáng lưu ý về cách ghi:
 *   1. Ghi nguyên tử: ghi ra file .tmp rồi rename. Nếu process chết giữa
 *      lúc ghi thì file chính vẫn còn nguyên bản cũ, không bị cắt dở.
 *   2. Tuần tự hoá: mọi lần ghi xếp hàng qua một promise chain, vì Server
 *      Action có thể chạy đồng thời.
 *   3. Giữ một bản .bak của lần ghi trước, để còn đường lùi nếu file chính
 *      bị hỏng vì lý do ngoài dự kiến.
 */

const DEFAULT_DIR = path.resolve(process.cwd(), "..", "..", "data");

export function dataDir(): string {
  return process.env.DATA_DIR
    ? path.resolve(process.env.DATA_DIR)
    : DEFAULT_DIR;
}

export function dataFilePath(): string {
  return path.join(dataDir(), "builder-data.json");
}

// ── Tuần tự hoá ghi ────────────────────────────────────────────────────

let writeChain: Promise<unknown> = Promise.resolve();

function enqueue<T>(job: () => Promise<T>): Promise<T> {
  const next = writeChain.then(job, job);
  writeChain = next.catch(() => undefined);
  return next;
}

async function writeAtomic(target: string, contents: string): Promise<void> {
  await mkdir(path.dirname(target), { recursive: true });
  const tmp = `${target}.tmp`;

  await writeFile(tmp, contents, "utf8");

  // Giữ bản cũ làm .bak, bỏ qua nếu chưa có file nào
  try {
    await rename(target, `${target}.bak`);
  } catch {
    // lần ghi đầu tiên, chưa có file để backup
  }

  try {
    await rename(tmp, target);
  } catch {
    // Một số filesystem không cho rename đè, ghi thẳng là phương án cuối
    await writeFile(target, contents, "utf8");
  }
}

export function save(): Promise<void> {
  return enqueue(async () => {
    const data = engine.snapshot();
    await writeAtomic(dataFilePath(), JSON.stringify(data, null, 2));
  });
}

// ── Nạp ────────────────────────────────────────────────────────────────

function isDataFile(value: unknown): value is DataFile {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<DataFile>;
  return Array.isArray(candidate.tasks) && Array.isArray(candidate.projects);
}

export function migrate(data: DataFile): DataFile {
  if (data.schema_version > SCHEMA_VERSION) {
    throw new Error(
      `File dữ liệu dùng schema_version ${data.schema_version}, ` +
      `bản web này chỉ đọc được tới ${SCHEMA_VERSION}. Cập nhật app.`,
    );
  }

  // v1 → v2: bổ sung deleted_at.
  //
  // Bắt buộc phải làm, không phải cho gọn. Engine phân biệt task còn sống
  // bằng `deleted_at === null`; nếu field là undefined thì mọi task cũ sẽ
  // bị coi như đã xoá và biến mất khỏi UI.
  if (data.schema_version < 2) {
    let backfilled = 0;
    for (const task of data.tasks) {
      if (task.deleted_at === undefined) {
        task.deleted_at = null;
        backfilled += 1;
      }
    }
    if (backfilled > 0) {
      console.info(
        `[store] migrate v1→v2: đặt deleted_at=null cho ${backfilled} task`,
      );
    }
    data.schema_version = 2;
  }

  // v2 → v3: bổ sung mảng `notes`.
  //
  // Phải backfill thành mảng rỗng, không để undefined. Engine gọi
  // state().notes.filter(...) ngay khi đọc; undefined sẽ ném TypeError và
  // làm cả store không nạp được, không chỉ mất phần sổ tay.
  if (data.schema_version < 3) {
    if (!Array.isArray(data.notes)) {
      data.notes = [];
      console.info("[store] migrate v2→v3: thêm mảng notes rỗng");
    }
    data.schema_version = 3;
  }

  // v4 → v5: bổ sung `scope` cho task, suy từ source.
  //
  // Bắt buộc phải làm. Engine lọc theo `scope === "personal"` / `"work"`; task
  // thiếu scope sẽ biến mất khỏi mọi view. Chỉ đặt cho task CHƯA có giá trị
  // hợp lệ, nên chạy lại (hoặc nạp file đã là v5) không đảo lựa chọn của User.
  if (data.schema_version < 5) {
    data.schema_version = 5;
  }

  // v5 → v6: bổ sung `sync_urls`. Phải là mảng chuỗi, nếu không code gọi .includes/.push sẽ ném.
  if (data.schema_version < 6) {
    data.schema_version = 6;
  }
  data.sync_urls = Array.isArray(data.sync_urls)
    ? data.sync_urls.filter((u): u is string => typeof u === "string")
    : [];

  // v6 → v7: bổ sung `due_all_day`. Cùng heuristic với backfill của migration backend:
  // task Jira có `due_at` đúng 00:00:00 UTC là hạn cả ngày (cả hai đường sync Jira chỉ sinh
  // giá trị đó từ `duedate`). Thiếu bước này, mọi hạn Jira cũ vẫn bị báo quá hạn từ 07:00 sáng.
  // Chỉ đặt cho task CHƯA có giá trị boolean nên chạy lại không đảo dữ liệu.
  if (data.schema_version < 7) {
    let flagged = 0;
    for (const task of data.tasks) {
      if (typeof task.due_all_day !== "boolean") {
        task.due_all_day =
          task.source === "jira" &&
          typeof task.due_at === "string" &&
          /T00:00:00(\.0+)?Z$/.test(task.due_at);
        if (task.due_all_day) flagged += 1;
      }
    }
    if (flagged > 0) {
      console.info(`[store] migrate v6→v7: đánh dấu hạn cả ngày cho ${flagged} task Jira`);
    }
    data.schema_version = 7;
  }
  // Lớp bảo vệ như scope bên dưới: file tự khai v7 nhưng thiếu/rác field vẫn không làm
  // engine hiểu sai (`undefined` là falsy nên an toàn, nhưng ghi ra file thì phải là boolean).
  for (const task of data.tasks) {
    if (typeof task.due_all_day !== "boolean") task.due_all_day = false;
  }

  // Chuẩn hoá scope LUÔN chạy, kể cả file tự khai schema_version 5: file đến từ
  // bên ngoài (restore JSON) có thể mang scope rác ('admin', '', object, vắng).
  // Giá trị hợp lệ được giữ nguyên nên không đảo lựa chọn của User.
  let normalized = 0;
  for (const task of data.tasks) {
    if (parseScope(task.scope) === null) {
      task.scope = defaultScopeFor(task.source);
      normalized += 1;
    }
  }
  if (normalized > 0) {
    console.info(`[store] migrate: chuẩn hoá scope cho ${normalized} task theo source`);
  }

  return data;
}

/**
 * State phải sống qua các lần hot reload của Next dev, nếu không mỗi lần
 * sửa file là dữ liệu trong RAM bị dựng lại và ghi đè file trên đĩa.
 */
const globalCache = globalThis as typeof globalThis & {
  __builderStoreReady?: Promise<void>;
};

async function initialise(): Promise<void> {
  const file = dataFilePath();

  try {
    const raw = await readFile(file, "utf8");
    const parsed: unknown = JSON.parse(raw);
    if (!isDataFile(parsed)) {
      throw new Error("Cấu trúc file không hợp lệ");
    }
    const data = migrate(parsed);
    engine.restore(data);
    console.info(
      `[store] đã nạp ${data.tasks.length} task và ${data.notes.length} note từ ${file}`,
    );

    // Dọn thùng rác quá hạn ngay khi khởi động. Chưa có scheduler nên đây
    // là điểm dọn tự động duy nhất ngoài lúc mở trang thùng rác.
    const purged = engine.purgeExpired();
    if (purged > 0) {
      console.info(`[store] đã xoá vĩnh viễn ${purged} task quá hạn giữ`);
    }
    const purgedNotes = engine.purgeExpiredNotes();
    if (purgedNotes > 0) {
      console.info(`[store] đã xoá vĩnh viễn ${purgedNotes} note quá hạn giữ`);
    }
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT") {
      console.info(`[store] chưa có ${file}, tạo dữ liệu mẫu`);
      engine.seed();
    } else {
      console.error(
        `[store] không đọc được ${file}: ${error instanceof Error ? error.message : String(error)
        }`,
      );
      console.error("[store] dùng dữ liệu mẫu, file cũ vẫn giữ nguyên");
      engine.seed();
      // Không ghi đè file đang lỗi, để bạn còn cơ hội sửa tay
      return;
    }
  }

  engine.setChangeHandler(() => {
    void save().catch((error: unknown) => {
      console.error("[store] ghi file thất bại:", error);
    });
  });

  await save();
}

export function ensureLoaded(): Promise<void> {
  globalCache.__builderStoreReady ??= initialise();
  return globalCache.__builderStoreReady;
}
