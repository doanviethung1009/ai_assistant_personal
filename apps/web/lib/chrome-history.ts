import { exec } from "child_process";
import fs from "fs";
import path from "path";
import util from "util";
import os from "os";

const execPromise = util.promisify(exec);

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
    throw new Error(`Không tìm thấy file Local State tại: ${localStatePath}. Chrome có thể chưa được cài đặt.`);
  }

  const raw = fs.readFileSync(localStatePath, "utf8");
  const state = JSON.parse(raw);
  const infoCache = state?.profile?.info_cache || {};

  const profiles: ChromeProfile[] = [];

  for (const [folder, info] of Object.entries(infoCache)) {
    const profileInfo = info as Record<string, any>;
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

/**
 * Trích xuất lịch sử Chrome từ file SQLite.
 * @param limit Số lượng bản ghi tối đa
 * @param customPath Đường dẫn tuỳ chỉnh tới file History (nếu không truyền sẽ dùng path mặc định theo OS)
 */
export async function scrapeChromeHistory(limit: number = 2000, customPath?: string): Promise<{ count: number; savedPath: string }> {
  const chromeHistoryPath = customPath || getChromeHistoryPath();

  if (!fs.existsSync(chromeHistoryPath)) {
    throw new Error(`Không tìm thấy file Chrome History tại: ${chromeHistoryPath}`);
  }

  // Copy ra thư mục tmp để tránh lỗi file locked do Chrome đang mở
  const tmpHistoryPath = path.join(os.tmpdir(), "temp_chrome_history.sqlite");
  fs.copyFileSync(chromeHistoryPath, tmpHistoryPath);

  // Dùng sqlite3 qua command line để đọc dữ liệu
  // Lưu ý: Trên Windows yêu cầu phải có sqlite3.exe trong PATH
  const query = `
    SELECT 
      url, 
      title, 
      visit_count, 
      datetime((last_visit_time/1000000)-11644473600, 'unixepoch', 'localtime') as last_visit_time 
    FROM urls 
    ORDER BY last_visit_time DESC 
    LIMIT ${limit};
  `;

  try {
    const { stdout } = await execPromise(`sqlite3 -json "${tmpHistoryPath}" "${query}"`);
    const historyData = JSON.parse(stdout || "[]");

    // Ghi vào file data trong thư mục dự án
    const targetDir = path.join(process.cwd(), "../../data");
    if (!fs.existsSync(targetDir)) fs.mkdirSync(targetDir, { recursive: true });

    const outPath = path.join(targetDir, "chrome-history.json");
    
    const finalData = {
      synced_at: new Date().toISOString(),
      source_path: chromeHistoryPath,
      items: historyData
    };

    fs.writeFileSync(outPath, JSON.stringify(finalData, null, 2));

    return { count: historyData.length, savedPath: outPath };
  } catch (err: any) {
    if (err.message.includes("sqlite3: command not found") || err.message.includes("is not recognized")) {
      throw new Error("Lỗi: Máy tính của bạn chưa cài đặt 'sqlite3' CLI. Trên Windows, hãy tải sqlite-tools và thêm vào PATH.");
    }
    throw err;
  } finally {
    // Luôn xóa file tạm sau khi xong (dù thành công hay lỗi) để giải phóng bộ nhớ đĩa
    try {
      if (fs.existsSync(tmpHistoryPath)) {
        fs.unlinkSync(tmpHistoryPath);
        console.log(`[chrome-history] Đã xóa file tạm: ${tmpHistoryPath}`);
      }
    } catch {
      // Bỏ qua lỗi xóa file tạm
    }
  }
}
