# Kiến thức & API Tích hợp Jira (Jira Sync)

Tài liệu này lưu trữ các kiến thức và luồng API đã được cài đặt trong hệ thống để đồng bộ Task từ Jira về hệ thống cá nhân, phục vụ cho việc maintain, mở rộng hoặc viết thêm AI Agent Skills liên quan đến Jira.

## 1. Phương thức Xác thực (Authentication)
Dự án hiện chốt sử dụng **Jira Cloud**.
- **Auth Mode**: HTTP Basic Auth.
- **Credentials**: `Email` và `API Token` (Tạo từ màn hình Security của Atlassian account).
- **Header gửi đi**: `Authorization: Basic base64(email:token)`.

## 2. API Đọc Dữ liệu (Search JQL)
Chúng ta dùng endpoint `/rest/api/3/search/jql` bằng phương thức `POST`.

### Body Request
```json
{
  "jql": "project in (\"OM\") ORDER BY updated DESC",
  "maxResults": 100,
  "fields": ["*all"],
  "expand": "names"
}
```
- `maxResults = 100` để tối ưu số lần gọi (phân trang bằng `nextPageToken` nếu có).
- `fields: ["*all"]` và `expand: "names"`: BẮT BUỘC để lấy toàn bộ các Custom Field (mã ngẫu nhiên như `customfield_10014`) và tên gốc của field đó (nằm trong object `names` trả về).

### Chế độ Fast Fetch (Cập nhật nhanh)
Khi user bấm "Cập nhật" (tức là đã đồng bộ trước đó và có `since`), ứng dụng sẽ chèn thêm một mệnh đề thời gian tương đối vào JQL:
`AND updated >= -Nm` (N là số phút từ lần đồng bộ cuối cộng thêm 5 phút bù trừ).
Kỹ thuật này giúp tránh lỗi lệch múi giờ (timezone issues) so với việc dùng timestamp cụ thể.

## 3. Quy trình Bóc tách Dữ liệu (Parsing Flow)
File thực thi chính: `apps/web/app/jira-actions.ts`.

### 3.1. Phân loại Trạng thái (Status)
- Nếu `status.name` chứa `progress`, `doing`, `review` -> `in_progress`.
- Nếu `status.name` chứa `done`, `close`, `resolved` -> `done`.
- Còn lại -> `todo`.

### 3.2. Bóc tách Nhãn (Tags) & Dự án (Projects)
Để phân loại task dễ dàng trên UI mà không cần User nhập tay:
1. **Dự án ưu tiên**: Đọc các Custom Field có tên liên quan đến `Company`, `Group`, `Customer`, `Team`... Nếu tìm thấy, lấy giá trị đó gán làm tên dự án (`project.name`).
2. **Dự án mặc định**: Nếu không có Custom Field, fallback về `fields.project.key` (Jira Project gốc).
3. **Dự án cuối cùng**: Nếu mất cả `fields.project`, lấy **Prefix** của mã Task (ví dụ `OM-123` -> lấy `OM`).
4. **Các Tags khác**: Tự động gom `labels`, `components`, `fixVersions`, `issuetype`, `parent` Epic vào mảng `tags` của Task.

### 3.3. Xử lý Dữ liệu Nội dung (Description)
- API v2 trả về chuỗi text (`string`).
- API v3 (Atlassian Document Format - ADF) trả về dạng JSON block. Hiện tại hệ thống tự fallback thành một dòng text tĩnh nếu phát hiện là object để tránh crash UI. (Có thể mở rộng render ADF trong tương lai).

## 4. Skills & Khuyến nghị khi AI thao tác với Jira
Nếu bạn (AI Agent) nhận được yêu cầu sửa lỗi liên quan đến Jira Sync:
1. **Luôn kiểm tra `jira-actions.ts`**: Đây là nơi duy nhất call ra API bên ngoài.
2. **Không đổi sang OAuth 2.0**: Trừ khi User yêu cầu rõ ràng, vì OAuth 2.0 (3LO) setup rất phức tạp (cần redirect URI, ngrok). Hiện Basic Auth là đủ cho personal store.
3. **Chú ý giới hạn rate limit**: Các vòng lặp fetch của Jira chỉ chặn ở `pagesFetched < 100` (10.000 task) để chống treo app.
