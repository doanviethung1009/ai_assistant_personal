# Hướng dẫn sử dụng API (API Reference)

Tài liệu này tổng hợp các API chính của backend (FastAPI) để người dùng hoặc các AI Agent khác có thể dễ dàng hiểu và gọi đúng endpoint khi cần thao tác dữ liệu.

Tất cả các endpoint dưới đây đều bắt đầu với tiền tố: `/api/v1`

## 1. API Quản lý Công việc (Tasks)
Base path: `/api/v1/tasks`

Các API này hỗ trợ việc quản lý công việc (Task), theo dõi tiến độ và xem báo cáo.

| Phương thức | Endpoint | Chức năng | Ghi chú |
|-------------|----------|-----------|---------|
| `GET` | `/agenda` | Lấy danh sách task cần làm hôm nay | Tự động tính toán deadline, ghim, v.v. |
| `GET` | `/stats` | Thống kê nhanh | Trả về tổng số task, đã hoàn thành, quá hạn, và `by_project`: tiến độ từng project (`total`, `done`, `open`, `percent_done` = done / task chưa huỷ; tối đa 50 dòng, nhiều việc đang mở nhất lên trước; task không có project gom vào một dòng `project_id = null`) |
| `GET` | `/participation` | Tỉ lệ tham dự dự án của nhóm | Task công việc chưa huỷ (gồm cả đã xong). Tham số `person` lặp lại để chọn người (tối đa 50, mỗi tên 1 đến 200 ký tự; bỏ trống = tất cả). Trả `assignees` (để dựng ô chọn), `selected`, và `projects[]` với `members[]` = `{assignee, count, done, open, percent}` (`count` = `done` + `open`). `percent` = count / **tổng task của project** (kể cả người không được chọn và task chưa giao) nên không đổi theo danh sách chọn. Tên không có task nào không gây lỗi, chỉ không sinh dòng. Lọc thời gian bằng `date_from` / `date_to` (ngày địa phương theo múi giờ hiển thị, **gồm cả ngày cuối**, bỏ trống một đầu = không giới hạn; đảo đầu cuối trả `422`), theo **ngày hoạt động**: `completed_at` với task đã xong, `updated_at` với task còn lại. Bộ lọc áp cho cả tử lẫn mẫu số; danh sách `assignees` vẫn là mọi thời gian để ô chọn người không biến mất |
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

## 2b. API Quản lý Tag (Tags)
Base path: `/api/v1/tags`

Tag không có bảng riêng: chúng là cột mảng `tags` trên `tasks` và `notes`, nên không cần migration.
Tên tag được chuẩn hoá như lúc nhập (chữ thường, space → `-`, tối đa 64 ký tự). Bản ghi đã xoá mềm bị bỏ qua. Web gọi qua `lib/api.ts` (`getTagsStatsApi`, `renameGlobalTagApi`, `deleteGlobalTagApi`), trang `/tags`. Cập nhật 2026-10-16 (T6).

| Phương thức | Endpoint | Chức năng | Ghi chú |
|-------------|----------|-----------|---------|
| `GET` | `/stats` | Mọi tag kèm `task_count`, `note_count` | Đếm trên task user nhìn thấy (work + personal của mình) và note của mình. Không phân trang: số tag riêng biệt nhỏ |
| `PATCH` | `/{name}` | Đổi tên tag. Body `{"new_name": "..."}` | Tên mới đã có trên cùng bản ghi thì gộp. Trả `{tasks, notes, rule}`: số bản ghi đã đổi và quy tắc đồng bộ vừa ghi (`rule` là `null` nếu không chạm task work). 404 nếu không có bản ghi nào sửa được; 409 nếu tên mới trùng tên cũ; 422 nếu tên rỗng |
| `DELETE` | `/{name}` | Xoá tag khỏi mọi bản ghi sửa được | Trả `{tasks, notes, rule}`; 404 nếu không có gì để xoá |

Phạm vi sửa (đổi tên/xoá): note của chính user, task `personal` của chính user, và task `work` chỉ khi có quyền `task:write_any_work` (lead, admin). Member vẫn thấy tag của task work trong `/stats` nhưng đổi tên/xoá không động vào chúng (kể cả task họ tạo hoặc được giao). Mỗi task bị đổi ghi một `TaskEvent` `updated` với payload `{tags: {from, to}}`. Tên tag có `/` vẫn dùng được (route `/{name:path}`).

**Ghi nhớ khi đồng bộ (T7):** đổi tên/xoá tag mà chạm ít nhất một task `work` (chỉ người có `task:write_any_work`) sẽ ghi một quy tắc vào bảng `tag_rules`. Quy tắc được áp lên tag ĐẾN TỪ NGUỒN NGOÀI (Jira connector, Excel, URL qua `upsert-batch`) nên tag đã đổi tên/xoá không quay lại; Jira connector áp quy tắc trước khi cắt còn 20 tag. Tag người dùng tự gõ trong form task/note không bị chặn, và tag đang có trên task không bị lọc. Hai lệnh này lấy khoá nhập nên có thể trả 409 nếu đang có lô đồng bộ chạy quá 5 giây. Quy tắc tạo trước khi có T7 không tồn tại: lead cần đổi tên/xoá lại tag cũ một lần. Chế độ `DATA_SOURCE=file` không có quy tắc.

### Quy tắc đồng bộ tag
Base path: `/api/v1/tag-rules` (cố ý không đặt dưới `/tags` vì `/tags/{name:path}` nuốt mọi đường con).

| Phương thức | Endpoint | Chức năng | Ghi chú |
|-------------|----------|-----------|---------|
| `GET` | `/` | Danh sách quy tắc, sắp theo `source_tag` | Mọi user đăng nhập. Query `limit` (1..200, mặc định 50), `offset`. Trả `Page`: item `{id, source_tag, target_tag, kind, created_by_user_id, created_by_name, created_at, updated_at}`; `kind` là `alias` hoặc `block` (`target_tag` null) |
| `DELETE` | `/{rule_id}` | Gỡ quy tắc | 204. Cần `task:write_any_work` (403), 404 nếu không có, 422 id sai. Lần đồng bộ tới tag nguồn sẽ quay lại. Ghi `audit_log` `tag_rule_deleted` (đặt quy tắc ghi `tag_rule_set`) |

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

Tham số của cả hai endpoint:

| Tham số | Kiểu | Ghi chú |
|---------|------|---------|
| `dry_run` | query, bool, mặc định `true` | `true`: chạy thử rồi rollback, trả báo cáo (kèm diff từng bản ghi sẽ bị ghi đè). Chỉ `dry_run=false` mới ghi thật |
| `expect_replaced` | query, int | **Bắt buộc khi nhập thật.** Số bản ghi sẽ bị ghi đè theo báo cáo dry-run; lệch thì huỷ (`replace_count_mismatch`) |
| `expect_sha256` | query, 64 ký tự hex | **Bắt buộc khi nhập thật.** `file_sha256` của báo cáo dry-run; file khác thì huỷ (`file_changed_since_dry_run`) |
| `include_personal` | query, bool, mặc định `false` (chỉ `/datafile`) | Mặc định nhập **bỏ qua** task `personal` đang có trong Postgres (đếm `skipped_personal`, không ghi đè). `true` cho phép ghi đè cả task cá nhân |

Mã lỗi: `401/403` thiếu hoặc sai khoá, `409` đang có lần nhập khác hoặc hết thời gian khoá dòng, `413` body trên 10 MB, `422` JSON sai hoặc thiếu tham số bắt buộc. Một request là một transaction (all-or-nothing); nhập thật trả `committed=true` kèm `import_id`. File phiên bản 5, 6 hoặc 7 đều được nhận; `meta.current_users` và `sync_urls` trong file cũng được nhập (thực thể `setting` trong báo cáo, `counts.settings`).

## 6. API Cài đặt (Settings) và danh sách người giao việc
Base path: `/api/v1`. Cài đặt **không bí mật** của người dùng, lưu ở bảng `app_settings` (khoá khai báo cứng, khoá lạ bị từ chối).

Múi giờ **không** nằm ở đây: hệ thống dùng một múi giờ của server (biến `TZ`/`DISPLAY_TIMEZONE`, xem `GET /system/info`). Các endpoint `/settings/display-timezone`, `/settings/timezones` và `PUT /me/timezone` đã gỡ (2026-10-13).

| Phương thức | Endpoint | Body / Trả về | Ràng buộc |
|-------------|----------|---------------|-----------|
| `GET`, `PUT` | `/settings/current-users` | `{"names": [...]}` | Tối đa 20 tên, mỗi tên 1 đến 200 ký tự (cắt khoảng trắng, loại trùng). Web truyền danh sách này làm `owner` cho `view=mine` |
| `GET`, `PUT` | `/settings/sync-urls` | `{"urls": [...]}` | Tối đa 50 URL, **chỉ `https`**, host thuộc allowlist: `docs.google.com`, `drive.google.com`, `drive.usercontent.google.com`, `*.googleusercontent.com`, `*.sharepoint.com`, `onedrive.live.com`, `1drv.ms`; thêm host qua biến `SYNC_URL_EXTRA_HOSTS` (host phải có dấu chấm; wildcard `*.X` bị từ chối nếu X là hậu tố dùng chung như `github.io`, `nip.io`, `herokuapp.com`, `co.uk`). Từ chối `user:pass@`, cổng lạ, IP, scheme khác |
| `GET` | `/tasks/assignees` | `["Tên", ...]` | Chỉ task còn sống và `scope=work`, tối đa 500 tên, sắp theo chữ cái |

Allowlist được kiểm **hai lần**: backend khi lưu, web khi fetch (kiểm lại URL ở mỗi bước chuyển hướng, tối đa 5 bước). `GET /settings/sync-urls` trả nguyên dữ liệu đã lưu, không kiểm lại. Chạy đồng bộ từ URL ở chế độ api cần pha B4.

## 7. (Đã gỡ) API Lịch sử duyệt web

Tính năng lịch sử duyệt web (pha B3) đã **gỡ hẳn** theo quyết định của User (nhánh `chore/remove-browser-history`, migration `d7e2a9c4b1f6` xoá bảng `browser_history`). File `data/chrome-history.json` của User được giữ nguyên, hệ thống không còn đọc hay ghi nó.

## 8. API Tích hợp (Integrations) và upsert hàng loạt (pha B4a)

Lưu kết nối Jira ở server (token mã hoá Fernet bằng `INTEGRATION_SECRET_KEY`, **không bao giờ** trả về) và ghi task từ nguồn ngoài. Mọi route cần `X-API-Key`.

| Method | Path | Ghi chú |
|---|---|---|
| `GET` | `/integrations?limit=&offset=` | `Page[...]` (mặc định 50, tối đa 100). Chỉ có `has_secret` và `secret_last4` |
| `POST` | `/integrations` | `{kind:"jira", name, base_url, account_email, token, config}`. `base_url` chỉ `https://host` (không IP, không cổng, không path, không `localhost`/`.local`/`.internal`). Token 8 đến 512 ký tự, chỉ ghi. Thiếu `INTEGRATION_SECRET_KEY` mà có token thì 503. Trùng `(kind, name)` thì 409 |
| `PATCH` | `/integrations/{id}` | Không gửi token thì giữ token cũ; `clear_token:true` để xoá. **Đổi `base_url` khi đang có token thì bắt buộc gửi token mới hoặc `clear_token`** (chặn gửi token cũ sang host khác) |
| `DELETE` | `/integrations/{id}` | Xoá kết nối |
| `POST` | `/tasks/upsert-batch` | **Cần quyền admin (`data:import` / `integration:manage`).** `{source, items[] <= 1000}`, trần body 20 MB. `source` khác `manual`. Upsert theo `(source, external_id)` trên task còn sống. Trả `{added, updated, unchanged, skipped_personal, errors[], warnings[]}` |
| `POST` | `/integrations/{id}/sync?since=&assignee=&reporter=` | **Cần quyền admin (`data:import` / `integration:manage`).** Chạy sync Jira Cloud ngay (polling, không webhook). `since` là ngày ISO tuỳ chọn (đồng bộ gia tăng). `assignee` và `reporter` (đều lặp được, tối đa 20 tên, mỗi tên 1 đến 100 ký tự) chỉ kéo issue của những người đó: có cả hai thì nối `OR` và bọc ngoặc, rồi AND vào JQL của kết nối, giúp lượt kéo nhỏ. Lượt có `assignee`/`reporter` không cập nhật `last_sync_at`. `TaskRead` có thêm `reporter` (tên hiển thị Jira, nullable, luôn theo Jira, không có email); `POST/PATCH /tasks` không nhận `reporter`. Trả `{fetched, pages, added, updated, unchanged, skipped_personal, errors[], warnings[], truncated}`. 409: đang có sync khác của kết nối này, hoặc thiếu token. 422: `since`/JQL/host bị chặn. 502/504: lỗi mạng hoặc Jira (thông báo cố định, không kèm body Jira). 503: giải mã token thất bại, cần nhập lại token |

Sync Jira (B4b) chạy **trong core** bằng connector Python (ngoại lệ D-B4a, xem `.agents/rules/project.md`):
- Chỉ Jira Cloud. `base_url` phải là `https://<tên>.atlassian.net`; core phân giải DNS, **chặn mọi IP riêng/loopback/metadata**, ghim đúng IP đã kiểm khi kết nối (chống DNS rebinding), không theo redirect, không gửi `Authorization` sang host khác.
- Giới hạn: 100 trang, 30 giây mỗi request, 5 phút cả lần, 10 MB mỗi trang, 50 MB cả lần (vượt thì `truncated=true`, `last_sync_at` không đổi).
- JQL mặc định dùng `current_users` (cài đặt B2); tên người dùng được escape.
- Tương đương chế độ file: `priority`, `due_at`, `assignee` và project chỉ được ghi khi **tạo** task, task cũ giữ giá trị bạn đã sửa. Title, status, tags (gộp), `description` (chỉ khi rỗng) vẫn cập nhật.
- Task bị bỏ qua nếu `external_url` thuộc host khác kết nối đang sync. Tối đa 50 project mới mỗi lần sync.
- `raw_payload` chỉ giữ một tập field được phép, không lưu cả issue.

Quy tắc `upsert-batch`:
- Chỉ ghi `scope=work`. Task trùng khoá mà đang `personal` thì **không bị ghi đè** (đếm vào `skipped_personal`).
- Chỉ ghi các trường client có gửi. **tags được gộp** (union; tag nguồn đi qua `tag_rules` trước khi gộp), **`description` chỉ điền khi task đang rỗng**. `completed_at` và `created_at` lấy từ nguồn nếu có.
- `raw_payload` được lọc khoá và giá trị nhạy cảm (Authorization, token, Bearer, JWT...); quá 64 KB (sau lọc) hoặc 256 KB (trước lọc) thì **vẫn upsert task**, bỏ payload và trả `warnings`.
- Idempotent: gửi lại cùng lô thì `added=0`, `updated=0`, không đổi `updated_at`, không sinh event. Event `synced` khi tạo, `updated` kèm diff khi đổi (actor `integration:<source>`).
- Xung đột với thao tác đồng thời (khoá dòng, lock `builder:import`) trả 409, thử lại được.
- Xoay khoá: đặt khoá mới ở `INTEGRATION_SECRET_KEY` và khoá cũ ở `INTEGRATION_SECRET_KEY_OLD`.

## 9. API Đăng nhập nội bộ và Quản trị người dùng

Base path: `/api/v1`. Mọi route cần `X-API-Key`; trừ `/auth/*` đều cần thêm JWT từng người (web ký, 60 giây). Spec: `docs/specs/admin-users-local-login.md`. Lỗi có dạng `{"detail": str, "code"?: str}`.

### 9.1. Đăng nhập và tài khoản của tôi

| Method | Path | Xác thực | Chức năng | Lỗi chính |
|---|---|---|---|---|
| `POST` | `/auth/login/password` | chỉ API key | Đăng nhập tài khoản nội bộ: `{identifier, password, client_ip?}` (identifier có `@` là email, không có là username). Trả `LoginResult` như `/auth/login` | 403 `invalid_credentials` (sai mật khẩu, không có tài khoản, đang bị khoá: một thông báo chung), 403 `password_login_disabled` (khi `PASSWORD_LOGIN_ENABLED=false`), 429 |
| `POST` | `/auth/login` | chỉ API key | Đăng nhập Google. Email trùng tài khoản nội bộ bị từ chối | 403 `account_mismatch` |
| `GET` | `/me` | JWT | Hồ sơ; thêm `auth_provider`, `username`, `must_change_password` | 401 |
| `POST` | `/me/password` | JWT | Tự đổi mật khẩu `{current_password, new_password}`; thành công thì `sv+1` (đăng xuất thiết bị khác). Được phép khi đang bị ép đổi | 409 `not_local_account`, 422 `current_password_invalid` \| `weak_password`, 429 |

Quy tắc: mật khẩu băm argon2id; sai 5 lần liên tiếp thì khoá 15 phút; mật khẩu tạm hết hạn sau 72 giờ và buộc đổi ở lần đăng nhập đầu. Khi `must_change_password`, mọi route khác (kể cả `/admin/*`) trả 403 `password_change_required` cho tới khi đổi xong. Mật khẩu không bao giờ nằm trong response, log hay audit.

### 9.2. Quản trị (`/admin`, cần quyền `user:manage`)

| Method | Path | Chức năng | Lỗi chính |
|---|---|---|---|
| `GET` | `/admin/users` | Danh sách phân trang (`q`, `role`, `status`, `auth_provider`, `locked`, `limit` ≤ 200 mặc định 50, `offset`); mỗi dòng có `aliases`, `is_env_admin` | 403 |
| `POST` | `/admin/users` | Mời một email Google: `{email, role, name?, aliases?}`. Trả `UserInvited` (= `UserAdminRead` + `aliases_skipped`) | 409 `email_exists` |
| `POST` | `/admin/users/local` | Tạo tài khoản nội bộ: `{username, email, name?, role, aliases?}`. Trả 201 `{user, temporary_password, aliases_skipped}`, `Cache-Control: no-store`; mật khẩu tạm chỉ hiện một lần | 409 `email_exists` \| `username_exists` |
| `GET` / `PATCH` | `/admin/users/{id}` | Xem / đổi `role`, `status`, `name`, `email`, `username` (hai trường cuối chỉ tài khoản nội bộ) | 409 `self_lockout` \| `last_admin` \| `env_admin` \| `not_local_account` |
| `POST` | `/admin/users/{id}/reset-password` | Cấp lại mật khẩu tạm (chỉ nội bộ, `sv+1`) | 409 `not_local_account` \| `self_action` |
| `POST` | `/admin/users/{id}/unlock` | Mở khoá tạm (204) | 404 |
| `POST` | `/admin/users/{id}/revoke-sessions` | Thu hồi mọi phiên (`sv+1`, 204) | 404 |
| `PUT` | `/admin/users/{id}/aliases` | Thay toàn bộ alias Jira `{aliases: [{source:"jira", alias}]}` (≤ 20) | 409 `alias_taken` |
| `DELETE` | `/admin/users/{id}` | Xoá user chưa có dữ liệu (204) | 409 `has_data` \| `self_lockout` \| `last_admin` \| `env_admin` |
| `GET` | `/admin/audit-log` | Nhật ký phân trang, lọc `action`, `actor_user_id`, `target_id`, `since`, `until` | 403, 422 |

**Alias lúc tạo/mời:** `aliases` là tên hiển thị của người đó trên Jira (khớp với `assignee`/`reporter` khi sync). Alias đang thuộc người khác **không làm hỏng yêu cầu**: user vẫn được tạo, tên bị bỏ qua nằm trong `aliases_skipped` để UI cảnh báo.

Quy tắc khoá admin (một nơi, `user_service`): không hạ/khoá/xoá admin hoạt động cuối cùng (`last_admin`), không tự hạ/khoá/xoá chính mình (`self_lockout`), không đụng email trong `ADMIN_EMAILS` (`env_admin`).

### 9.3. CLI phá kính (`python -m app.cli.auth`, qua `make`)

`create-local`, `reset-password`, `unlock` (mật khẩu tạm in một lần ra stdout), cùng `enable|disable|revoke|alias|invite|token|bootstrap`. CLI dùng chung `user_service` với API nên ghi audit giống nhau (`via:"cli"`), nhưng không bị chặn bởi `last_admin`/`self_lockout` (chỉ cảnh báo). Biến môi trường: `PASSWORD_LOGIN_ENABLED` (mặc định `true`, `false` là công tắc tắt đăng nhập mật khẩu khi bị tấn công dò).

---

> 💡 **Lưu ý quan trọng cho AI Agent (LLM):**
> - Payload dữ liệu của các API cập nhật (PATCH) và sinh log (event) là **JSONB**, nên trước khi gọi API phải map đúng cấu trúc từ điển.
> - Các API `/{id}` bắt buộc phải đặt sau các route tĩnh như `/agenda` hay `/stats` để tránh lỗi FastAPI 422. Điều này đã được cấu hình chuẩn trong router.
> - `deleted_at`: Các API danh sách (`/`) luôn tự động loại bỏ các bản ghi đã xoá (deleted_at IS NOT NULL). Chỉ có endpoint `/trash` mới hiển thị những bản ghi này.
