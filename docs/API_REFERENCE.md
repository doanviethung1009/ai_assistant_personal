# Hướng dẫn sử dụng API (API Reference)

Tài liệu này tổng hợp các API chính của backend (FastAPI) để người dùng hoặc các AI Agent khác có thể dễ dàng hiểu và gọi đúng endpoint khi cần thao tác dữ liệu.

Tất cả các endpoint dưới đây đều bắt đầu với tiền tố: `/api/v1`

## 1. API Quản lý Công việc (Tasks)
Base path: `/api/v1/tasks`

Các API này hỗ trợ việc quản lý công việc (Task), theo dõi tiến độ và xem báo cáo.

| Phương thức | Endpoint | Chức năng | Ghi chú |
|-------------|----------|-----------|---------|
| `GET` | `/agenda` | Lấy danh sách task cần làm hôm nay | Tự động tính toán deadline, ghim, v.v. |
| `GET` | `/stats` | Thống kê nhanh | Trả về tổng số task, đã hoàn thành, quá hạn |
| `GET` | `/trash` | Thùng rác | Các task đã xoá mềm (Soft delete) |
| `POST` | `/sync` | Đồng bộ dữ liệu | Đồng bộ task từ nguồn ngoài (Jira, CSV...) |
| `POST` | `/wipe` | Dọn dẹp dữ liệu | Xoá vĩnh viễn (Hard delete) dựa theo cờ |
| `GET` | `/` | Danh sách task | Trả về danh sách có phân trang (Pagination) |
| `POST` | `/` | Tạo task mới | Bắt buộc có Title |
| `GET` | `/{task_id}` | Chi tiết task | Trả về chi tiết kèm nhật ký (History logs) |
| `PATCH` | `/{task_id}` | Cập nhật bán phần | Sửa đổi title, description, due_date... |
| `DELETE` | `/{task_id}` | Xoá mềm task | Task sẽ bị đưa vào `/trash` |
| `POST` | `/{task_id}/restore` | Khôi phục task | Đưa task từ thùng rác trở lại |
| `POST` | `/{task_id}/complete`| Đánh dấu xong | Chuyển trạng thái sang "Hoàn thành" |
| `POST` | `/{task_id}/reopen` | Mở lại task | Đưa task về trạng thái chưa làm |

## 2. API Quản lý Ghi chú (Notes)
Base path: `/api/v1/notes`

Danh sách (`GET /`) và `GET /stats` nhận thêm tham số `archived` (bool, mặc định `false`): `false` chỉ trả note đang dùng, `true` chỉ trả note đã lưu trữ. `offset` tối đa 1 000 000. Chi tiết: `docs/specs/note-archive.md`.

Notes khác với Tasks ở chỗ nó không có vòng đời (chưa làm/hoàn thành) và không có deadline. Dùng để lưu trữ kiến thức, snippet, hoặc ghi chú rời rạc.

| Phương thức | Endpoint | Chức năng | Ghi chú |
|-------------|----------|-----------|---------|
| `GET` | `/tags` | Lấy danh sách thẻ | Lấy tất cả tag đang dùng cho notes |
| `POST` | `/sync` | Đồng bộ note | Nhập dữ liệu note từ bên ngoài |
| `POST` | `/wipe` | Dọn dẹp note | Xoá vĩnh viễn (Hard delete) |
| `GET` | `/trash` | Thùng rác note | Các note đã xoá mềm |
| `GET` | `/` | Danh sách note | Trả về danh sách có phân trang |
| `POST` | `/` | Tạo note mới | |
| `GET` | `/{note_id}` | Chi tiết note | |
| `PATCH` | `/{note_id}` | Cập nhật note | Cập nhật title, content, is_pinned... |
| `DELETE` | `/{note_id}` | Xoá mềm note | Note sẽ bị đưa vào `/trash` |
| `POST` | `/{note_id}/restore` | Khôi phục note | |
| `POST` | `/{note_id}/archive` | Lưu trữ note | Ẩn khỏi danh sách mặc định, không bị dọn như thùng rác. Gọi lặp lại trả 200 và giữ `archived_at` lần đầu. 404 nếu note không có hoặc đang trong thùng rác |
| `POST` | `/{note_id}/unarchive` | Bỏ lưu trữ | Idempotent như trên |
| `POST` | `/{note_id}/pin` | Ghim / Bỏ ghim | Toggle trạng thái ghim của note lên đầu |

## 3. API Quản lý Dự án (Projects)
Base path: `/api/v1/projects`

Projects dùng để nhóm các Tasks lại với nhau.

| Phương thức | Endpoint | Chức năng |
|-------------|----------|-----------|
| `GET` | `/` | Danh sách project |
| `POST` | `/` | Tạo project mới |
| `GET` | `/{project_id}` | Chi tiết project |
| `PATCH` | `/{project_id}` | Cập nhật project |
| `DELETE`| `/{project_id}` | Xoá project |

## 4. API Hệ thống (System)
Base path: `/api/v1/system`

| Phương thức | Endpoint | Chức năng |
|-------------|----------|-----------|
| `GET` | `/db-stats` | Trạng thái DB |

---

> 💡 **Lưu ý quan trọng cho AI Agent (LLM):**
> - Payload dữ liệu của các API cập nhật (PATCH) và sinh log (event) là **JSONB**, nên trước khi gọi API phải map đúng cấu trúc từ điển.
> - Các API `/{id}` bắt buộc phải đặt sau các route tĩnh như `/agenda` hay `/stats` để tránh lỗi FastAPI 422. Điều này đã được cấu hình chuẩn trong router.
> - `deleted_at`: Các API danh sách (`/`) luôn tự động loại bỏ các bản ghi đã xoá (deleted_at IS NOT NULL). Chỉ có endpoint `/trash` mới hiển thị những bản ghi này.
