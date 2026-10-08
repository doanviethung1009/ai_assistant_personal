import "server-only";

import { execFile } from "child_process";
import fs from "fs";
import path from "path";
import util from "util";
import os from "os";

const execFilePromise = util.promisify(execFile);

export interface ChromeHistoryEntry {
  url: string;
  title: string;
  visit_count: number;
  last_visit_time: string; // ISO String
}

function getChromeBaseDir(): string {
  const platform = os.platform();
  const home = os.homedir();

  switch (platform) {
    case 'darwin':
      return path.join(home, "Library/Application Support/Google/Chrome");
    case 'win32':
      return path.join(home, "AppData/Local/Google/Chrome/User Data");
    case 'linux':
      return path.join(home, ".config/google-chrome");
    default:
      throw new Error(`Nền tảng ${platform} chưa được hỗ trợ mặc định.`);
  }
}

function getChromeHistoryPath(): string {
  return path.join(getChromeBaseDir(), "Default/History");
}

export interface ChromeProfile {
  folder: string;       // "Default", "Profile 1", "Profile 3", ...
  name: string;         // Tên hiển thị ("Work", "MAS-Group", ...)
  email: string;        // Email (Gmail) đã đăng nhập
  historyPath: string;  // Đường dẫn tuyệt đối tới file History
  hasHistory: boolean;  // Có file History hay không
}

/**
 * Liệt kê tất cả Chrome profile trên máy bằng cách đọc file Local State.
 * Trả về danh sách profile kèm tên hiển thị, email, và đường dẫn file History.
 */
export async function listChromeProfiles(): Promise<ChromeProfile[]> {
  const baseDir = getChromeBaseDir();
  const localStatePath = path.join(baseDir, "Local State");

  if (!fs.existsSync(localStatePath)) {
    throw new Error("Không tìm thấy thư mục Chrome trên máy chạy web. Chrome có thể chưa được cài đặt.");
  }

  const raw = fs.readFileSync(localStatePath, "utf8");
  const state = JSON.parse(raw) as { profile?: { info_cache?: Record<string, unknown> } };
  const infoCache = state?.profile?.info_cache || {};

  const profiles: ChromeProfile[] = [];

  for (const [folder, info] of Object.entries(infoCache)) {
    const profileInfo = info as Record<string, string | undefined>;
    const historyPath = path.join(baseDir, folder, "History");
    
    profiles.push({
      folder,
      name: profileInfo.name || folder,
      email: profileInfo.user_name || profileInfo.gaia_name || profileInfo.gaia_given_name || "",
      historyPath,
      hasHistory: fs.existsSync(historyPath),
    });
  }

  // Sắp xếp: profile có History lên trước
  profiles.sort((a, b) => (a.hasHistory === b.hasHistory ? 0 : a.hasHistory ? -1 : 1));

  return profiles;
}

/** Giới hạn số dòng mỗi lần cào; khớp trần một lô batch của core. */
export const MAX_SCRAPE_LIMIT = 10_000;

/**
 * Ép `limit` về số nguyên trong 1..10 000.
 *
 * Giá trị này được nội suy vào câu SQL (sqlite3 CLI không có tham số bind), nên chỉ
 * chấp nhận số nguyên thật: chuỗi, NaN, số thực đều bị từ chối thay vì làm tròn ngầm.
 */
export function parseScrapeLimit(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 1 || value > MAX_SCRAPE_LIMIT) {
    throw new Error(`limit phải là số nguyên từ 1 đến ${MAX_SCRAPE_LIMIT}`);
  }
  return value;
}

/**
 * Xác định file History hợp lệ, bắt buộc nằm dưới thư mục Chrome của user.
 *
 * `customPath` do client gửi qua Server Action nên là input không tin cậy: không
 * chặn thì có thể trỏ `../../etc/...` hoặc một symlink để copy file bất kỳ. Dùng
 * realpath ở CẢ hai phía để symlink không thoát ra ngoài, và bắt tên file đúng là
 * "History" để không đọc nhầm file khác trong thư mục Chrome (Cookies, Login Data).
 */
function resolveHistoryPath(customPath?: string): string {
  let baseReal: string;
  try {
    baseReal = fs.realpathSync(getChromeBaseDir());
  } catch {
    // Không lộ đường dẫn máy ra browser.
    throw new Error("Không tìm thấy thư mục Chrome trên máy chạy web");
  }
  const candidate = customPath ? path.resolve(customPath) : getChromeHistoryPath();

  let real: string;
  try {
    real = fs.realpathSync(candidate);
  } catch {
    throw new Error("Không tìm thấy file Chrome History ở đường dẫn đã chọn");
  }
  if (!real.startsWith(baseReal + path.sep) || path.basename(real) !== "History") {
    throw new Error("Đường dẫn phải là file History nằm trong thư mục Chrome của bạn");
  }
  return real;
}

/**
 * Copy file History ra `dest` qua MỘT fd đã mở.
 *
 * Chống TOCTOU: kiểm tra (realpath) rồi mới copy bằng đường dẫn thì giữa hai bước file
 * có thể bị thay bằng symlink. O_NOFOLLOW chặn symlink ở thành phần cuối, fstat kiểm
 * tra đúng fd đang đọc là file thường. O_NOFOLLOW không có trên Windows nên bỏ qua ở đó.
 */
function copyHistoryViaFd(real: string, dest: string): void {
  const noFollow = fs.constants.O_NOFOLLOW ?? 0;
  let src: number;
  try {
    src = fs.openSync(real, fs.constants.O_RDONLY | noFollow);
  } catch {
    throw new Error("Không mở được file Chrome History");
  }
  try {
    if (!fs.fstatSync(src).isFile()) throw new Error("Đường dẫn không phải file");
    const dst = fs.openSync(dest, "w", 0o600);
    try {
      const buf = Buffer.allocUnsafe(1024 * 1024);
      let n: number;
      while ((n = fs.readSync(src, buf, 0, buf.length, null)) > 0) {
        fs.writeSync(dst, buf, 0, n);
      }
    } finally {
      fs.closeSync(dst);
    }
  } finally {
    fs.closeSync(src);
  }
}

/**
 * "local": 'YYYY-MM-DD HH:MM:SS' theo giờ máy, giữ nguyên định dạng chrome-history.json cũ.
 * "utc": ISO 8601 có hậu tố Z, dùng khi đẩy lên core (upsert chỉ tăng nên giờ lệch lên
 * trước sẽ không tự sửa được, vì vậy tuyệt đối không dùng 'localtime' ở nhánh này).
 */
export type ScrapeTimeMode = "local" | "utc";

export interface ScrapeResult {
  items: ChromeHistoryEntry[];
  /** Tên thư mục profile ("Default", "Profile 1"), không phải đường dẫn. */
  profile: string;
  /** Đường dẫn tuyệt đối đã kiểm tra, chỉ dùng cho chế độ file. */
  sourcePath: string;
}

/**
 * Trích xuất lịch sử Chrome từ file SQLite.
 *
 * Không ghi gì ra đĩa dự án: caller quyết định ghi file (chế độ file) hay đẩy lên
 * core (chế độ api).
 * @param limit Số bản ghi tối đa, số nguyên 1..10 000
 * @param customPath File History tuỳ chọn, phải nằm dưới thư mục Chrome
 * @param timeMode Kiểu giờ trả về, xem ScrapeTimeMode
 */
export async function scrapeChromeHistory(
  limit: number = 2000,
  customPath?: string,
  timeMode: ScrapeTimeMode = "local",
): Promise<ScrapeResult> {
  const safeLimit = parseScrapeLimit(limit);
  const chromeHistoryPath = resolveHistoryPath(customPath);

  // Thư mục tạm riêng mỗi lần chạy: tên ngẫu nhiên, không đoán trước được và không đụng nhau
  const workDir = fs.mkdtempSync(path.join(os.tmpdir(), "chrome-history-"));
  const tmpHistoryPath = path.join(workDir, "History.sqlite");

  try {
    // Copy ra tmp để tránh lỗi file locked do Chrome đang mở
    copyHistoryViaFd(chromeHistoryPath, tmpHistoryPath);

    // Lưu ý: Trên Windows yêu cầu phải có sqlite3.exe trong PATH
    // Epoch WebKit = micro giây từ 1601-01-01; 11644473600 là số giây tới 1970-01-01.
    // ORDER BY dùng urls.last_visit_time (số) vì alias cùng tên sẽ che cột và sắp theo chuỗi.
    const timeExpr = "(urls.last_visit_time/1000000)-11644473600";
    const timeSql =
      timeMode === "utc"
        ? `strftime('%Y-%m-%dT%H:%M:%SZ', ${timeExpr}, 'unixepoch')`
        : `datetime(${timeExpr}, 'unixepoch', 'localtime')`;
    const query = `SELECT url, title, visit_count, ${timeSql} AS last_visit_time FROM urls ORDER BY urls.last_visit_time DESC LIMIT ${safeLimit};`;

    // execFile: không qua shell nên không có nội suy/chuyển hướng; đối số là mảng.
    // maxBuffer 256 MB đủ cho 10 000 dòng với URL dài.
    const { stdout } = await execFilePromise("sqlite3", ["-json", tmpHistoryPath, query], {
      maxBuffer: 256 * 1024 * 1024,
    });
    const parsed: unknown = JSON.parse(stdout.trim() || "[]");
    if (!Array.isArray(parsed)) throw new Error("sqlite3 trả về dữ liệu không phải mảng");

    const items: ChromeHistoryEntry[] = [];
    for (const row of parsed as Array<Record<string, unknown>>) {
      if (typeof row.url !== "string" || typeof row.last_visit_time !== "string") continue;
      items.push({
        url: row.url,
        title: typeof row.title === "string" ? row.title : "",
        visit_count: typeof row.visit_count === "number" ? row.visit_count : 0,
        last_visit_time: row.last_visit_time,
      });
    }

    return { items, profile: path.basename(path.dirname(chromeHistoryPath)), sourcePath: chromeHistoryPath };
  } catch (err) {
    // Chi tiết (câu SQL, đường dẫn tmp) chỉ ở log server, không trả ra browser.
    const message = err instanceof Error ? err.message : String(err);
    if (message.includes("ENOENT") && message.includes("sqlite3")) {
      throw new Error("Máy chạy web chưa cài đặt 'sqlite3' CLI. Trên Windows, hãy tải sqlite-tools và thêm vào PATH.");
    }
    console.error("scrapeChromeHistory thất bại:", message);
    if (err instanceof Error && /^(Không|Đường dẫn|limit)/.test(err.message)) throw err;
    throw new Error("sqlite3 đọc file History thất bại");
  } finally {
    // Luôn xóa thư mục tạm (dù thành công hay lỗi)
    try {
      fs.rmSync(workDir, { recursive: true, force: true });
    } catch {
      // Bỏ qua lỗi xóa file tạm
    }
  }
}

/** Chế độ file: ghi đè data/chrome-history.json như hành vi cũ. */
export function saveChromeHistoryFile(result: ScrapeResult): string {
  const targetDir = path.join(process.cwd(), "../../data");
  if (!fs.existsSync(targetDir)) fs.mkdirSync(targetDir, { recursive: true });
  const outPath = path.join(targetDir, "chrome-history.json");
  const finalData = {
    synced_at: new Date().toISOString(),
    source_path: result.sourcePath,
    items: result.items,
  };
  fs.writeFileSync(outPath, JSON.stringify(finalData, null, 2));
  return outPath;
}
