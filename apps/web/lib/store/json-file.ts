import "server-only";

import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

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

export function aiLogsFilePath(): string {
  return path.join(dataDir(), "ai-logs.json");
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

export function saveAiLogs(): Promise<void> {
  return enqueue(async () => {
    const data = engine.snapshotAiLogs();
    await writeAtomic(aiLogsFilePath(), JSON.stringify(data, null, 2));
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

  // Không còn migrate ai_logs chung vào DataFile (SCHEMA_VERSION = 4).
  // Đã dọn dẹp logic ai_logs.

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
  
  // Khởi tạo file ai-logs.json
  await initialiseAiLogs();
}

async function initialiseAiLogs(): Promise<void> {
  const file = aiLogsFilePath();
  try {
    const raw = await readFile(file, "utf8");
    const parsed: unknown = JSON.parse(raw);
    engine.restoreAiLogs(parsed as { ai_logs?: any[] });
    console.info(`[store] đã nạp ai_logs từ ${file}`);
  } catch (error) {
    console.info(`[store] chưa có ${file}, sẽ tạo mới khi có dữ liệu.`);
    engine.restoreAiLogs({ ai_logs: [] });
  }

  engine.setAiLogsChangeHandler(() => {
    void saveAiLogs().catch((error: unknown) => {
      console.error("[store] ghi file ai-logs thất bại:", error);
    });
  });
}

export function ensureLoaded(): Promise<void> {
  globalCache.__builderStoreReady ??= initialise();
  return globalCache.__builderStoreReady;
}
