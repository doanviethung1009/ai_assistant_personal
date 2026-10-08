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

**Loại việc (`scope`) và bộ lọc `view`.** Mỗi task có `scope`: `work` (công việc, thường từ Jira) hoặc `personal` (cá nhân). Mặc định theo nguồn: `jira`, `github`, `gitlab` là `work`; còn lại là `personal`. Sửa được bằng `PATCH` (đổi một task Jira sang `personal` nghĩa là tách nó khỏi đồng bộ). Chi tiết thiết kế: `docs/specs/task-scope.md`.

| Tham số (cho `GET /`, `/agenda`, `/stats`) | Ghi chú |
|---|---|
| `view` | `all` (mặc định ở API) / `mine` / `personal` / `work`. `mine` = việc cá nhân + việc công việc giao cho một tên trong `owner` + việc công việc bạn tự tạo (không `assignee`, không mã Jira). Web mặc định `mine` |
| `owner` | Lặp lại được, tối đa 20 tên (1 đến 200 ký tự), khớp chính xác; chỉ đi kèm `view=mine`. Sai thì 422 |

`trash_total` và `minutes_logged_today` trong `/stats` không lọc theo `view`. `TaskRead` luôn trả `scope`.

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

## 5. API Nhập dữ liệu hàng loạt (Import)
Base path: `/api/v1/import`

Đưa dữ liệu từ file JSON của web (chế độ file) vào Postgres. **GHI ĐÈ** bản ghi đã tồn tại, **không xoá** gì. Hướng dẫn từng bước và hoàn tác: `docs/DATA_MIGRATION_TO_POSTGRES.md`.

| Phương thức | Endpoint | Body | Chức năng |
|-------------|----------|------|-----------|
| `POST` | `/datafile` | Nội dung `builder-data.json` | Nhập project, task, task_events, note |
| `POST` | `/ai-logs` | Nội dung `ai-logs.json` | Nhập nhật ký AI |

Tham số của cả hai endpoint:

| Tham số | Kiểu | Ghi chú |
|---------|------|---------|
| `dry_run` | query, bool, mặc định `true` | `true`: chạy thử rồi rollback, trả báo cáo (kèm diff từng bản ghi sẽ bị ghi đè). Chỉ `dry_run=false` mới ghi thật |
| `expect_replaced` | query, int | **Bắt buộc khi nhập thật.** Số bản ghi sẽ bị ghi đè theo báo cáo dry-run; lệch thì huỷ (`replace_count_mismatch`) |
| `expect_sha256` | query, 64 ký tự hex | **Bắt buộc khi nhập thật.** `file_sha256` của báo cáo dry-run; file khác thì huỷ (`file_changed_since_dry_run`) |
| `include_personal` | query, bool, mặc định `false` (chỉ `/datafile`) | Mặc định nhập **bỏ qua** task `personal` đang có trong Postgres (đếm `skipped_personal`, không ghi đè). `true` cho phép ghi đè cả task cá nhân |
| `X-Import-Secret` | header | **Bắt buộc khi nhập thật.** Giá trị biến `IMPORT_COMMIT_SECRET` của core (tối thiểu 16 ký tự). Chưa cấu hình hoặc sai: `403`. Dry-run không cần |

Mã lỗi: `401/403` thiếu hoặc sai khoá, `409` đang có lần nhập khác hoặc hết thời gian khoá dòng, `413` body trên 10 MB, `422` JSON sai hoặc thiếu tham số bắt buộc. Một request là một transaction (all-or-nothing); nhập thật trả `committed=true` kèm `import_id`. File phiên bản 5 hoặc 6 đều được nhận; `meta.current_users` và `sync_urls` trong file cũng được nhập (thực thể `setting` trong báo cáo, `counts.settings`).

## 6. API Cài đặt (Settings) và danh sách người giao việc
Base path: `/api/v1`. Cài đặt **không bí mật** của người dùng, lưu ở bảng `app_settings` (khoá khai báo cứng, khoá lạ bị từ chối).

| Phương thức | Endpoint | Body / Trả về | Ràng buộc |
|-------------|----------|---------------|-----------|
| `GET`, `PUT` | `/settings/current-users` | `{"names": [...]}` | Tối đa 20 tên, mỗi tên 1 đến 200 ký tự (cắt khoảng trắng, loại trùng). Web truyền danh sách này làm `owner` cho `view=mine` |
| `GET`, `PUT` | `/settings/sync-urls` | `{"urls": [...]}` | Tối đa 50 URL, **chỉ `https`**, host thuộc allowlist: `docs.google.com`, `drive.google.com`, `drive.usercontent.google.com`, `*.googleusercontent.com`, `*.sharepoint.com`, `onedrive.live.com`, `1drv.ms`; thêm host qua biến `SYNC_URL_EXTRA_HOSTS` (host phải có dấu chấm; wildcard `*.X` bị từ chối nếu X là hậu tố dùng chung như `github.io`, `nip.io`, `herokuapp.com`, `co.uk`). Từ chối `user:pass@`, cổng lạ, IP, scheme khác |
| `GET` | `/tasks/assignees` | `["Tên", ...]` | Chỉ task còn sống và `scope=work`, tối đa 500 tên, sắp theo chữ cái |

Allowlist được kiểm **hai lần**: backend khi lưu, web khi fetch (kiểm lại URL ở mỗi bước chuyển hướng, tối đa 5 bước). `GET /settings/sync-urls` trả nguyên dữ liệu đã lưu, không kiểm lại. Chạy đồng bộ từ URL ở chế độ api cần pha B4.

## 7. API Lịch sử duyệt web (Browser history, pha B3)

Dữ liệu cá nhân nhạy cảm. Web đọc Chrome trên máy chạy web rồi đẩy lên core. Mọi route cần `X-API-Key`. URL được chuẩn hoá khi lưu: chỉ `http`/`https`, **bỏ query, fragment và userinfo** (nhưng **path vẫn giữ**, nên link kiểu `/reset-password/<token>` vẫn nằm trong DB).

| Method | Path | Ghi chú |
|---|---|---|
| `POST` | `/browser-history/batch` | `{profile, items:[{url,title,visit_count,last_visit_time}]}`, tối đa 10 000 item (vượt thì 422). Upsert theo `(profile, sha256(url))`, `visit_count` và `last_visit_at` chỉ tăng (GREATEST). Trả `{received, created, updated, unchanged, invalid}`. `last_visit_time` có hậu tố `Z`/offset thì dùng đúng; không có múi giờ thì hiểu theo `display_timezone` |
| `GET` | `/browser-history?q=&profile=&limit=50&offset=` | `Page[...]`, `limit` tối đa 100, sắp theo `last_visit_at` giảm dần |
| `DELETE` | `/browser-history?profile=` | `profile` bắt buộc. **Cần header `X-Import-Secret`** (xoá cứng, không hoàn tác). Trả `{deleted}` |
| `POST` | `/import/browser-history?dry_run=true&profile=Default` | Nhập `chrome-history.json` (body thô, tối đa 10 MB, 50 000 dòng). Nhập thật (`dry_run=false`) cần `X-Import-Secret`; không dùng `expect_sha256` vì upsert chỉ tăng nên không ghi đè xuống; không ghi `import_runs`, chỉ log một dòng (profile, số lượng, sha256, IP) |

Giới hạn đã biết: `COUNT(*)` chạy mỗi lần tải trang; tìm kiếm `q` dùng ILIKE không index (đủ cho quy mô cá nhân); muốn đặt lại `visit_count` thấp hơn phải xoá theo profile rồi đẩy lại.

---

> 💡 **Lưu ý quan trọng cho AI Agent (LLM):**
> - Payload dữ liệu của các API cập nhật (PATCH) và sinh log (event) là **JSONB**, nên trước khi gọi API phải map đúng cấu trúc từ điển.
> - Các API `/{id}` bắt buộc phải đặt sau các route tĩnh như `/agenda` hay `/stats` để tránh lỗi FastAPI 422. Điều này đã được cấu hình chuẩn trong router.
> - `deleted_at`: Các API danh sách (`/`) luôn tự động loại bỏ các bản ghi đã xoá (deleted_at IS NOT NULL). Chỉ có endpoint `/trash` mới hiển thị những bản ghi này.
