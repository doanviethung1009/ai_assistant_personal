"use server";

import * as api from "@/lib/api";
import { CoreApiError } from "@/lib/api";
import { listChromeProfiles, saveChromeHistoryFile, scrapeChromeHistory } from "@/lib/chrome-history";
import type { BrowserHistoryBatchResult, BrowserHistoryImportReport } from "@/lib/types";
import { revalidatePath } from "next/cache";

const MAX_IMPORT_BYTES = 8 * 1024 * 1024;

function errorText(error: unknown): string {
  if (error instanceof CoreApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

/** Tên profile là nhãn thư mục: không đường dẫn, không ký tự điều khiển, tối đa 200. */
function validProfile(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.trim().length > 0 &&
    value.length <= 200 &&
    !/[\x00-\x1f\x7f/\\]/.test(value) &&
    value !== "." &&
    value !== ".."
  );
}

export interface SyncChromeResult {
  ok: boolean;
  error?: string;
  count?: number;
  /** Chế độ file: nơi đã ghi file. */
  path?: string;
  /** Chế độ api: kết quả upsert trên core. */
  pushed?: BrowserHistoryBatchResult;
  profile?: string;
}

/**
 * Cào lịch sử Chrome trên máy chạy web, rồi lưu.
 *
 * Chế độ file: ghi data/chrome-history.json như cũ. Chế độ api: đẩy lên core theo lô
 * (profile = tên thư mục), không ghi file. Server Action là endpoint công khai nên
 * kiểu của mọi tham số được kiểm lại ở đây, không tin chữ ký TypeScript.
 */
export async function syncChromeHistoryAction(limit: unknown = 2000, customPath?: unknown): Promise<SyncChromeResult> {
  if (typeof limit !== "number") return { ok: false, error: "limit phải là số" };
  if (customPath !== undefined && customPath !== null && typeof customPath !== "string") {
    return { ok: false, error: "customPath phải là chuỗi" };
  }
  try {
    // Chế độ file giữ giờ 'localtime' như chrome-history.json cũ; chế độ api đẩy giờ UTC (hậu tố Z).
    const res = await scrapeChromeHistory(limit, customPath || undefined, api.IS_LOCAL ? "local" : "utc");
    if (api.IS_LOCAL) {
      const savedPath = saveChromeHistoryFile(res);
      revalidatePath("/history");
      revalidatePath("/data");
      return { ok: true, count: res.items.length, path: savedPath };
    }
    const pushed = await api.pushBrowserHistory(
      res.profile,
      res.items.map((it) => ({
        url: it.url,
        title: it.title,
        visit_count: it.visit_count,
        // ISO UTC có hậu tố Z: core không phải đoán múi giờ.
        last_visit_at: it.last_visit_time,
      })),
    );
    revalidatePath("/history");
    revalidatePath("/data");
    return { ok: true, count: res.items.length, pushed, profile: res.profile };
  } catch (error) {
    return { ok: false, error: errorText(error) };
  }
}

/** Xoá lịch sử của một profile trên core (chỉ chế độ api). KHÔNG hoàn tác. */
export async function deleteChromeHistoryAction(
  profile: unknown,
  secret: unknown,
): Promise<{ ok: boolean; error?: string; deleted?: number }> {
  if (api.IS_LOCAL) return { ok: false, error: "Chỉ dùng được khi DATA_SOURCE=api" };
  if (!validProfile(profile)) return { ok: false, error: "Tên profile không hợp lệ" };
  // ASCII in được: giá trị đi vào header HTTP.
  if (typeof secret !== "string" || !/^[\x20-\x7e]{1,256}$/.test(secret)) {
    return { ok: false, error: "Chưa nhập mật khẩu (hoặc chứa ký tự không hợp lệ)." };
  }
  try {
    const res = await api.deleteBrowserHistory(profile.trim(), secret);
    revalidatePath("/history");
    return { ok: true, deleted: res.deleted };
  } catch (error) {
    if (error instanceof CoreApiError && error.status === 403) {
      return {
        ok: false,
        error:
          "Mật khẩu sai, hoặc core chưa cấu hình IMPORT_COMMIT_SECRET (đặt biến này trong .env của core rồi khởi động lại api).",
      };
    }
    // Không dùng errorText: tránh thông báo lỡ lặp lại mật khẩu.
    if (error instanceof CoreApiError) return { ok: false, error: error.message };
    console.error("xoá lịch sử Chrome thất bại", error instanceof Error ? error.name : "unknown");
    return { ok: false, error: "Không gọi được core API. Kiểm tra service api." };
  }
}

export interface ChromeImportResult {
  ok: boolean;
  error?: string;
  status?: number;
  report?: BrowserHistoryImportReport;
}

/**
 * Kiểm tra (dry_run) hoặc nhập thật chrome-history.json vào Postgres.
 *
 * Nhập thật cần mật khẩu IMPORT_COMMIT_SECRET; upsert chỉ-tăng nên không ghi đè xuống.
 * Mật khẩu chỉ đi qua header, không log và không lặp lại trong thông báo lỗi.
 */
export async function importChromeHistoryToCoreAction(formData: FormData): Promise<ChromeImportResult> {
  if (api.IS_LOCAL) return { ok: false, error: "Chỉ dùng được khi DATA_SOURCE=api", status: 501 };

  const file = formData.get("file");
  const dryRun = String(formData.get("dry_run") ?? "1") !== "0";
  const profileRaw = formData.get("profile");
  const profile = profileRaw === null || profileRaw === "" ? "Default" : profileRaw;

  if (!(file instanceof File) || file.size === 0) return { ok: false, error: "Chưa chọn file" };
  if (file.size > MAX_IMPORT_BYTES) return { ok: false, error: "File vượt quá 8 MB", status: 413 };
  if (!validProfile(profile)) return { ok: false, error: "Tên profile không hợp lệ" };

  let secret: string | undefined;
  if (!dryRun) {
    const raw = formData.get("import_secret");
    // ASCII in được: giá trị đi vào header HTTP.
    if (typeof raw !== "string" || !/^[\x20-\x7e]{1,256}$/.test(raw)) {
      return { ok: false, error: "Chưa nhập mật khẩu nhập dữ liệu (hoặc chứa ký tự không hợp lệ)." };
    }
    secret = raw;
  }

  let text: string;
  try {
    text = await file.text();
  } catch {
    return { ok: false, error: "Không đọc được nội dung file" };
  }

  try {
    const report = await api.importBrowserHistoryFile(text, { dryRun, profile: profile.trim(), secret });
    if (report.committed) {
      revalidatePath("/history");
      revalidatePath("/data");
    }
    return { ok: true, report };
  } catch (error) {
    if (error instanceof CoreApiError) {
      if (error.status === 403) {
        return {
          ok: false,
          status: 403,
          error:
            "Mật khẩu nhập sai, hoặc core chưa cấu hình IMPORT_COMMIT_SECRET (đặt biến này trong .env của core rồi khởi động lại api).",
        };
      }
      return { ok: false, error: error.message, status: error.status };
    }
    console.error("nhập lịch sử Chrome thất bại", error instanceof Error ? error.name : "unknown");
    return { ok: false, error: "Không gọi được core API. Kiểm tra service api." };
  }
}

/**
 * Liệt kê tất cả Chrome profile trên máy (tên hiển thị, email, đường dẫn).
 * Dùng để hiển thị dropdown cho user chọn profile cần cào lịch sử.
 */
export async function listChromeProfilesAction() {
  try {
    const profiles = await listChromeProfiles();
    return { ok: true, profiles };
  } catch (error) {
    return { ok: false, error: errorText(error), profiles: [] };
  }
}
