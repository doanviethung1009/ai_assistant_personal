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

function getChromeHistoryPath(): string {
  const platform = os.platform();
  const home = os.homedir();

  switch (platform) {
    case 'darwin': // macOS
      return path.join(home, "Library/Application Support/Google/Chrome/Default/History");
    case 'win32': // Windows
      return path.join(home, "AppData/Local/Google/Chrome/User Data/Default/History");
    case 'linux': // Linux
      return path.join(home, ".config/google-chrome/Default/History");
    default:
      throw new Error(`Nền tảng ${platform} chưa được hỗ trợ mặc định.`);
  }
}

export async function scrapeChromeHistory(limit: number = 2000): Promise<{ count: number; savedPath: string }> {
  const chromeHistoryPath = getChromeHistoryPath();

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

    // Xóa file tạm
    if (fs.existsSync(tmpHistoryPath)) fs.unlinkSync(tmpHistoryPath);

    // Ghi vào file data
    const targetDir = path.join(process.cwd(), "../../data");
    if (!fs.existsSync(targetDir)) fs.mkdirSync(targetDir, { recursive: true });

    const outPath = path.join(targetDir, "chrome-history.json");
    
    const finalData = {
      synced_at: new Date().toISOString(),
      items: historyData
    };

    fs.writeFileSync(outPath, JSON.stringify(finalData, null, 2));

    return { count: historyData.length, savedPath: outPath };
  } catch (err: any) {
    if (fs.existsSync(tmpHistoryPath)) fs.unlinkSync(tmpHistoryPath);
    if (err.message.includes("sqlite3: command not found") || err.message.includes("is not recognized")) {
      throw new Error("Lỗi: Máy tính của bạn chưa cài đặt 'sqlite3' CLI. Trên Windows, hãy tải sqlite-tools và thêm vào PATH.");
    }
    throw err;
  }
}
