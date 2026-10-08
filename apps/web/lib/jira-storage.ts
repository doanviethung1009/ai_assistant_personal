/**
 * Khoá localStorage của cấu hình Jira cũ (CHỈ chế độ file dùng làm nơi lưu). Chế độ api đọc
 * khoá này đúng một lần để chuyển lên server. Tách ra file riêng để component client chỉ
 * cần hằng số không phải import cả JiraSyncManager.
 */
export const STORAGE_KEY = "builder_jira_configs_v2";
