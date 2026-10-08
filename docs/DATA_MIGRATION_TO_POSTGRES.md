# Chuyển dữ liệu từ file JSON sang Postgres

> Dành cho bạn đang dùng web ở chế độ `DATA_SOURCE=file` (dữ liệu ở `data/builder-data.json`) và muốn chuyển sang Postgres (`DATA_SOURCE=api`) mà không mất dữ liệu.
> Thiết kế đầy đủ: `docs/specs/import-json-to-postgres.md`. Hiện **có pha B1** (task, project, note; nhật ký AI đã gỡ), **B2** (người dùng hiện tại, URL đồng bộ) và **B4** (kết nối Jira, upsert hàng loạt, sync Jira ở backend). Lịch sử Chrome (B3) đã gỡ hẳn, không còn chuyển (xem mục 6).

## 1. Cần biết trước khi làm

- **Nhập là GHI ĐÈ, không xoá.** Bản ghi trong file mà đã có trong Postgres (cùng `id`, hoặc cùng khoá tự nhiên) sẽ bị **thay bằng nội dung file**. Bản ghi chỉ có trong Postgres thì giữ nguyên. Không có chế độ xoá hàng loạt.
- **Rủi ro lớn nhất:** file cũ ghi đè trạng thái mới hơn trong Postgres (ví dụ bạn đã đổi trạng thái task qua web ở chế độ api, rồi nhập lại file cũ). Bước **Kiểm tra** luôn liệt kê từng bản ghi sẽ bị ghi đè kèm diff, và gắn nhãn "File cũ hơn dữ liệu hiện tại".
- **Web chưa có đăng nhập.** Vì vậy nhập thật bắt buộc **mật khẩu** (`IMPORT_COMMIT_SECRET`). Kiểm tra thì không cần.
- **Hai kho không tự đồng bộ.** Đổi nguồn không xoá dữ liệu bên kia, nhưng bạn sẽ không thấy nó cho tới khi đổi lại.

- **Mật khẩu nhập đi qua mạng dạng chữ thường** từ trình duyệt tới web. Dùng trên `localhost` thì không sao; khi chạy `make lan-up` trên wifi dùng chung, ai nghe lén được sẽ đọc được. Chỉ nhập thật trên máy của bạn.
- **Dùng mật khẩu do `make env` sinh** (96 bit). Core tối thiểu 16 ký tự nhưng không kiểm độ mạnh; `aaaaaaaaaaaaaaaa` vẫn qua. Đặt tay thì không để khoảng trắng ở đầu hoặc cuối.

## 2. Các bước

**Chạy theo đúng thứ tự.** Lần đầu sau khi kéo code mới nhất (B1 đến B4) có hai bẫy: image Docker phải build lại, và `.env` cũ không tự có biến mới.

0. **Điều kiện: cần Docker** (Postgres, Redis, api chạy trong container). Máy không có Docker thì **chỉ dùng được chế độ file** (`make web-local`): vẫn dùng bình thường, nhưng không có Postgres, không có kết nối Jira mã hoá, không có "Cào ngay" ở backend. Kiểm tra: `docker --version`.
1. **Sao lưu thư mục `data/` ra nơi khác trước khi bật web mới.** Lần nạp đầu của web mới sẽ ghi lại `data/builder-data.json` lên phiên bản mới (một chiều, bản cũ hơn không đọc lại được):
   ```bash
   cp -R data "data.bak-$(date +%Y%m%d)"
   ```
   Nếu đã có dữ liệu trong Postgres thì sao lưu luôn (sau khi stack đã chạy ở bước 4):
   ```bash
   make backup
   ```
2. **Build lại image.** Code mới thêm thư viện Python (`cryptography`, `httpcore`). `make up` **không** build lại, nên bỏ bước này thì api báo lỗi import và không khởi động:
   ```bash
   make build
   ```
3. **Tạo hoặc bổ sung `.env`** (chạy **ở thư mục gốc repo**, không phải `apps/web`, vì `Makefile` nằm ở gốc):
   - Chưa có `.env`: `make env` sinh đủ khoá ngẫu nhiên và in `API_KEY` cùng `IMPORT_COMMIT_SECRET` ra màn hình (mật khẩu bạn sẽ gõ ở bước Nhập thật). `INTEGRATION_SECRET_KEY` **không** được in.
   - Đã có `.env` từ trước: `make env-fill` chỉ thêm `IMPORT_COMMIT_SECRET` và `INTEGRATION_SECRET_KEY` nếu còn thiếu hoặc rỗng, **không đổi** biến đã có, và chỉ in tên biến. Muốn xem `IMPORT_COMMIT_SECRET` thì mở `.env` (quyền 600).
   - **Sao lưu `.env`.** Mất `INTEGRATION_SECRET_KEY` thì mọi token Jira đã lưu mất, phải nhập lại. Chưa có `IMPORT_COMMIT_SECRET` thì core từ chối nhập thật.
4. **Bật stack và đổi sang Postgres.** Api tự chạy migration khi khởi động:
   ```bash
   make up
   make use-db
   curl -s http://localhost:8000/health/ready
   ```
   `health/ready` phải trả OK (Postgres và Redis sẵn sàng). Lỗi thì xem log: `make logs-api`. Quay về chế độ file bất cứ lúc nào: đặt `DATA_SOURCE=file` trong `.env` rồi `make up`; dữ liệu ở hai kho không bị xoá.
5. **Lấy file dữ liệu để nhập.** Dùng thẳng `data/builder-data.json`, hoặc xuất từ web đang chạy chế độ file: trang Dữ liệu, tab **Xuất dữ liệu**, tải "JSON Toàn bộ Dữ liệu".
6. **Nhập:** trang Dữ liệu, tab **Nhập dữ liệu**, mục "Chuyển dữ liệu JSON vào Postgres":
   1. Chọn loại file và file (tối đa 8 MB).
   2. Bấm **Kiểm tra**. Chưa ghi gì. Đọc báo cáo: số tạo mới, ghi đè, không đổi, bỏ qua, lỗi.
   3. Nếu có **khung đỏ "bản ghi sẽ bị GHI ĐÈ"**: mở danh sách, xem diff từng bản ghi, tích các ô xác nhận.
   4. Gõ mật khẩu, bấm **Nhập thật**. Toàn bộ chạy trong một transaction (all-or-nothing).
7. **Kiểm tra lại:** bấm Kiểm tra với cùng file, kết quả phải là 0 tạo mới, 0 ghi đè (nhập lặp lại là an toàn).

8. **Jira (tuỳ chọn, chỉ Jira Cloud `*.atlassian.net`):** trang Dữ liệu, tab **Đồng bộ**, mục kết nối Jira.
   1. Nếu trình duyệt còn cấu hình Jira cũ (lưu ở `localStorage`), bấm **Chuyển các kết nối này lên server**. Chỉ mục nào server nhận thành công mới bị xoá khỏi trình duyệt; mục lỗi hiện nút **Bỏ khỏi trình duyệt**. Hoặc tạo kết nối mới bằng form (token chỉ ghi, không bao giờ hiện lại, chỉ thấy 4 ký tự cuối).
   2. Bấm **Cào ngay** ở kết nối, gõ mật khẩu nhập (`IMPORT_COMMIT_SECRET`). Lần đầu nên chạy không điền "Từ ngày"; về sau điền ngày để chỉ lấy phần thay đổi.
   3. Task đã có trong Postgres giữ nguyên priority, hạn, người giao và project bạn đã sửa; chỉ task **mới** nhận các giá trị đó từ Jira. Task Jira bạn đã chuyển sang `personal` không bị đụng.
   4. Báo "chạm trần 100 trang": thu hẹp JQL (cấu hình kết nối) hoặc dùng "Từ ngày".

### Lỗi thường gặp ở lần chạy đầu

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `make: *** No rule to make target 'env'` | Đang đứng ở `apps/web`, không phải thư mục gốc | `cd` về thư mục gốc repo |
| api không khởi động, log có `ModuleNotFoundError` (`cryptography`, `httpcore`) | Image chưa build lại sau khi kéo code | `make build` rồi `make up` |
| Tạo kết nối Jira báo 503 "thiếu khoá" | `.env` cũ không có `INTEGRATION_SECRET_KEY` | `make env-fill` rồi `make up` |
| Nhập thật báo 403 | Sai mật khẩu, hoặc `.env` cũ chưa có `IMPORT_COMMIT_SECRET` | `make env-fill`, mở `.env` lấy mật khẩu |
| "Cào ngay" báo 503 "nhập lại token" | `INTEGRATION_SECRET_KEY` đã đổi hoặc mất so với lúc lưu token | Nhập lại token của kết nối |
| "Cào ngay" báo 409 | Đang có lần sync khác của kết nối này, hoặc kết nối chưa có token | Chờ lần kia xong; nhập token |
| Kết nối Jira bị từ chối khi lưu | `base_url` không phải `https://<tên>.atlassian.net` (IP, cổng lạ, host khác) | Dùng đúng địa chỉ Jira Cloud; Jira tự cài đặt chưa hỗ trợ |

## 3. Core tự chuẩn hoá gì (có cảnh báo trong báo cáo)

| Trong file | Sau khi nhập | Lý do |
|---|---|---|
| Key project có khoảng trắng, dấu, chữ thường (`ONE NEXUS`, `SAO MỘC`, `KHÁC`) | `ONE_NEXUS`, `SAO_MOC`, `KHAC` (tên hiển thị giữ nguyên) | Backend chỉ nhận `A-Z`, `0-9`, `_`, bắt đầu bằng chữ |
| Màu `hsl(...)` | Màu hex `#rrggbb` | Cột màu của backend chỉ nhận hex |
| `external_url` không phải http/https | Bỏ, kèm cảnh báo | Chặn `data:` và scheme lạ |
| `raw_payload` | **Không nhận** | Là dữ liệu không đáng tin |
| Task `done` thiếu `completed_at` | Điền từ `updated_at` | Để thống kê "hoàn thành 7 ngày" đúng |
| Task thiếu `scope` (file phiên bản cũ) | Suy từ `source`: `jira`/`github`/`gitlab` là `work`, còn lại `personal` | Xem `docs/specs/task-scope.md` |

**Khi ghi đè,** các giá trị "dự phòng" nói trên **không** đè lên dữ liệu thật trong Postgres. Ví dụ file cũ không có `archived_at` thì note đã lưu trữ **không** bị bỏ lưu trữ; file thiếu `completed_at` thì ngày đóng thật trong DB được giữ.

**Task cá nhân được bảo vệ:** nếu trong Postgres đã có một task `scope=personal` trùng với task trong file (cùng `id` hoặc cùng `(source, external_id)`), lần nhập **bỏ qua** nó và đếm `skipped_personal`, không ghi đè. Muốn ghi đè cả task cá nhân thì bật ô "Ghi đè cả task cá nhân đang có trong Postgres" trong panel (hoặc `include_personal=true` khi gọi API); đây là lựa chọn có chủ ý, hãy xem kỹ danh sách ghi đè trước khi nhập thật.

Bản ghi đang ở **thùng rác** (trong DB hoặc trong file) bị bỏ qua, không bị hồi sinh.

## 4. Gọi thẳng bằng API (không cần web)

```bash
# Kiểm tra (an toàn, mặc định dry_run=true)
curl -X POST -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  --data-binary @data/builder-data.json \
  "http://localhost:8000/api/v1/import/datafile?dry_run=true"

# Nhập thật: cần mã băm file của báo cáo trên, số bản ghi ghi đè, và mật khẩu
curl -X POST -H "X-API-Key: $API_KEY" -H "X-Import-Secret: $IMPORT_COMMIT_SECRET" \
  -H "Content-Type: application/json" --data-binary @data/builder-data.json \
  "http://localhost:8000/api/v1/import/datafile?dry_run=false&expect_replaced=<N>&expect_sha256=<file_sha256>"
```

Lỗi thường gặp: `403` (sai mật khẩu hoặc chưa đặt `IMPORT_COMMIT_SECRET`), `409` (đang có lần nhập khác chạy), `413` (file lớn hơn 10 MB), `422` (thiếu `expect_*` khi nhập thật, hoặc JSON sai), và `committed=false` kèm `replace_count_mismatch` (dữ liệu đã đổi sau lần Kiểm tra) hoặc `file_changed_since_dry_run`.

## 5. Hoàn tác

Cách chắc chắn nhất là khôi phục từ bản sao lưu ở bước 1. Ngoài ra mỗi lần nhập thật ghi sổ cái vào hai bảng `import_runs` và `import_audit`: với mỗi bản ghi bị ghi đè, cột `before` giữ **toàn bộ giá trị trước khi ghi đè**; với mỗi bản ghi tạo mới, giữ `entity_id`.

> **Các câu SQL dưới đây chưa được chạy thử trên máy dev** (hook chặn `DELETE`/`TRUNCATE` qua `psql` và máy không có Docker). Luôn chạy trong `BEGIN; ... ROLLBACK;` trước, xem số dòng bị ảnh hưởng, rồi mới đổi thành `COMMIT;`. Id lần nhập có trong báo cáo, hoặc `SELECT id, created_at, counts FROM import_runs ORDER BY created_at DESC;`. Trong `psql`, đặt một lần rồi dùng `:'import_id'` (có dấu nháy; dán UUID trần vào câu SQL sẽ lỗi cú pháp):
>
> ```sql
> \set import_id 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'
> ```

Xem một lần nhập đã làm gì:

```sql
SELECT entity, action, count(*) FROM import_audit WHERE import_id = :'import_id' GROUP BY 1, 2;
```

Hoàn tác bản ghi **tạo mới**. Thứ tự quan trọng: xoá sự kiện trước (kể cả sự kiện được nhập vào task đã có sẵn, các sự kiện này không bị `CASCADE` vì task cha không bị xoá), rồi task, note, cuối cùng project:

```sql
BEGIN;
DELETE FROM task_events WHERE id IN (SELECT entity_id FROM import_audit WHERE import_id = :'import_id' AND entity = 'task_event' AND action = 'created');
DELETE FROM tasks       WHERE id IN (SELECT entity_id FROM import_audit WHERE import_id = :'import_id' AND entity = 'task'       AND action = 'created');
DELETE FROM notes       WHERE id IN (SELECT entity_id FROM import_audit WHERE import_id = :'import_id' AND entity = 'note'       AND action = 'created');
DELETE FROM projects    WHERE id IN (SELECT entity_id FROM import_audit WHERE import_id = :'import_id' AND entity = 'project'    AND action = 'created');
-- Kiểm tra nếu còn sót sự kiện do lần nhập sinh ra mà chưa có audit (lần nhập cũ):
SELECT count(*) FROM task_events WHERE actor LIKE 'import:%' AND payload->>'import_id' = :'import_id';
ROLLBACK;  -- đổi thành COMMIT khi đã kiểm tra số dòng
```

Ghi chú về nhật ký AI (đã gỡ): hạ migration `f3a8c1d5e7b9` chỉ tạo lại bảng `ai_logs` RỖNG; dòng `import_audit` có `entity='ai_log'` của các lần nhập cũ trỏ tới id không còn, đó là dấu vết lịch sử, không cần dọn. Muốn giữ dữ liệu bảng trước khi `make migrate`: `\copy ai_logs TO 'ai_logs_backup.csv' CSV HEADER`. Triển khai code mới (đã bỏ route) TRƯỚC khi chạy migration để API cũ không trả 500 ở giữa hai bước.

Hoàn tác bản ghi **bị ghi đè** (ví dụ trả lại `title` và `status` của task). Liệt kê đúng các cột cần trả, `before` chứa mọi cột:

```sql
BEGIN;
UPDATE tasks t
SET title = r.title, status = r.status, updated_at = r.updated_at
FROM import_audit a, LATERAL jsonb_populate_record(NULL::tasks, a.before) r
WHERE a.import_id = :'import_id' AND a.entity = 'task' AND a.action = 'replaced' AND t.id = a.entity_id;
ROLLBACK;  -- đổi thành COMMIT khi đã kiểm tra
```

Giới hạn đã biết: hoán vị khoá (`projects.key` hoặc `(source, external_id)`) giữa hai bản ghi trong cùng một file bị từ chối với lỗi `natural_key_conflict` vì unique index không cho UPDATE tuần tự. `import_audit` chưa có chính sách xoá cũ; `before` giữ bản sao đầy đủ nên nếu sau này bạn xoá hẳn một note từng chứa bí mật thì bản sao trong audit vẫn còn.

Nếu phải hạ migration `tasks.scope` (`alembic downgrade -1`) trên dữ liệu thật, các lựa chọn bạn đã sửa tay (task Jira chuyển thành cá nhân và ngược lại) sẽ mất. Lưu trước bằng:

```sql
COPY (SELECT id, scope FROM tasks
      WHERE scope <> CASE WHEN source IN ('jira','github','gitlab') THEN 'work' ELSE 'personal' END)
TO STDOUT WITH CSV HEADER;
```

**URL đồng bộ chỉ nhận một số host.** Khi lưu và khi fetch, URL phải là `https` và thuộc: Google Docs/Sheets/Drive (`docs.google.com`, `drive.google.com`, `drive.usercontent.google.com`, `*.googleusercontent.com`), SharePoint/OneDrive (`*.sharepoint.com`, `onedrive.live.com`, `1drv.ms`). **Link OneDrive cá nhân có thể cần thêm host** (OneDrive chuyển hướng tới host riêng như `*.files.1drv.com`; chưa kiểm được nên chưa đưa vào danh sách mặc định): thêm vào `SYNC_URL_EXTRA_HOSTS` sau khi tự kiểm. Host khác (ví dụ Jira on-prem) phải thêm vào biến `SYNC_URL_EXTRA_HOSTS` (danh sách phân cách dấu phẩy, **đặt giống nhau cho cả api và web** trong `.env`/compose; host phải có dấu chấm, wildcard `*.X` bị từ chối nếu X là hậu tố dùng chung như `github.io`, `nip.io`; cấu hình sai thì api không khởi động còn web từ chối tất cả). **Thay đổi hành vi:** trước đây chế độ file lưu URL bất kỳ; nay link ngoài danh sách bị từ chối ngay lúc lưu, vì chính server web sẽ fetch nó (chống SSRF).

## 6. Chưa chuyển (các pha sau)

| Thứ | Hiện tại | Kế hoạch |
|---|---|---|
| `current_users`, `sync_urls`, danh sách assignee | **Đã chuyển (B2):** lưu ở bảng `app_settings`, nhập từ `meta.current_users` và `sync_urls` của file | Xong |
| Lịch sử Chrome | **Đã gỡ hẳn (B3 bị bỏ):** không còn bảng, API hay trang `/history`; `data/chrome-history.json` giữ nguyên nhưng không còn được dùng | Không chuyển |
| URL/Excel sync | **Đã chuyển (B4a):** ở chế độ api web đọc file/URL rồi đẩy lên `upsert-batch`, cần mật khẩu. Dòng Excel thiếu Issue Key bị bỏ (đếm `skipped_no_key`) | Xong |
| Cấu hình Jira (token) | **Đã chuyển (B4a):** lưu ở server, token mã hoá bằng `INTEGRATION_SECRET_KEY`; có nút "Chuyển các kết nối này lên server" để đưa cấu hình cũ từ trình duyệt lên | Xong |
| Jira sync (cào) | **Đã chuyển (B4b):** ở chế độ api bấm "Cào ngay" cho từng kết nối (cần mật khẩu), core gọi Jira Cloud. Chỉ hỗ trợ `*.atlassian.net`; Jira tự cài đặt chưa hỗ trợ | Xong |
| **Vault** | **Cố ý KHÔNG chuyển.** Vẫn là file `data/vault.json`, độc lập với `DATA_SOURCE` | Không chuyển |

**Hệ quả khi đổi sang `DATA_SOURCE=api` ngay bây giờ:** Chế độ file vẫn dùng được độc lập (URL/Excel sync và lưu kết nối Jira đã chạy ở chế độ api) ("người dùng hiện tại", lọc task cá nhân/công việc và danh sách URL đồng bộ đã chạy ở chế độ api). Nếu bạn đang dùng các tính năng đó hằng ngày thì **đừng bỏ chế độ file** vội.

**Vault và sao lưu Postgres:** vì Vault nằm ngoài Postgres nên `pg_dump` **không** bao gồm nó. Hãy sao lưu riêng qua `/api/export?format=json&entity=vault` (tab Xuất dữ liệu, "JSON Két bảo mật").
