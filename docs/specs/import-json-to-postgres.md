# Spec: Chuyển dữ liệu chế độ file sang Postgres qua core API

- Trạng thái: **DRAFT v2** (đã có quyết định của User cho D1-D14, chờ User duyệt thiết kế các pha mới B2-B4)
- Tác giả: architect
- Ngày: 2026-10-07 (v1), cập nhật v2 cùng ngày
- Nhánh lúc viết: `feat/data-tab-cleanup`
- Alembic head lúc viết spec: `d4e9f2a6b8c5` (add notes.archived_at)
- Đã đối chiếu với code thật và với `data/builder-data.json`, `data/ai-logs.json`, `data/chrome-history.json` (chỉ đọc). Điểm lệch giữa giả định ban đầu và code nằm ở **Phụ lục A**.

## 0. Tóm tắt thay đổi v1 → v2

| Quyết định | v1 đề xuất | v2 (User chốt) |
|---|---|---|
| D4 bản ghi đã tồn tại | `skip` mặc định, `update_if_newer` tuỳ chọn | **Replace**: ghi đè bằng nội dung file. Bỏ `skip` và `update_if_newer`. Giữ rào chắn: dry-run mặc định, báo cáo diff từng bản ghi, không xoá hàng loạt, ghi event/audit cho mỗi bản ghi bị ghi đè. |
| D10 thứ ngoài thực thể | Ngoài phạm vi | **Làm cả**, chia thành 4 pha B1-B4 giao và merge độc lập. |
| D7 | Chuẩn hoá key, đổi màu hsl → hex | Giữ nguyên, có cảnh báo trong báo cáo. |
| D1-D3, D5, D6, D8, D9, D11-D14 | — | Duyệt theo đề xuất v1. D3 được làm rõ cho replace ở 2.2. |
| Migration B1 | Không có | **Có**: bảng `import_runs` và `import_audit` để ghi lại giá trị trước khi ghi đè (hệ quả của replace, xem D15). |

## 1. Các pha

| Pha | Nội dung | Migration | Phụ thuộc | Thay đổi bảo mật, cần `security-auditor` |
|---|---|---|---|---|
| **B1** | Nhập thực thể: projects, tasks, task_events, notes (file `builder-data.json`), ai_logs (file `ai-logs.json`). Replace có audit. | `import_runs`, `import_audit` | Không | **Có**: endpoint ghi hàng loạt có phá huỷ, Server Action mới |
| **B2** | Cài đặt người dùng: `current_users`, `sync_urls`, danh sách assignee ở chế độ api; nhập `meta.current_users` từ file. | `app_settings` | B1 (dùng lại service nhập, mở rộng phần `meta`) | **Có**: `sync_urls` là URL do người dùng nhập mà server sẽ fetch (SSRF) |
| **B3** | Vault (chỉ ciphertext) và lịch sử Chrome lưu ở Postgres khi `DATA_SOURCE=api`; nhập từ `vault.json`, `chrome-history.json`. | `vault_blobs`, `browser_history` | Không phụ thuộc B1/B2 về code; chỉ xếp hàng migration | **Có, bắt buộc**: Vault E2EE (zero-knowledge phải giữ), lịch sử duyệt web là dữ liệu cá nhân nhạy cảm, lỗ hổng shell injection có sẵn |
| **B4** | Jira sync chạy ở backend: lưu cấu hình kết nối (token mã hoá phía server), endpoint upsert hàng loạt cho integration, chạy sync theo yêu cầu; URL/Excel sync ở chế độ api dùng lại endpoint upsert. | `integration_connections` | B1 (chuẩn hoá key project), B2 (`current_users` cho JQL mặc định, `sync_urls`) | **Có, bắt buộc**: lưu token Jira ở server, outbound HTTP, dữ liệu ngoài không đáng tin |

**Thứ tự đề xuất:** B1 → B2 → B4. B3 làm song song với B2 hoặc B4 được, vì không chạm cùng file.

**Migration phải tuyến tính.** Mỗi pha tạo revision với `down_revision` là head **lúc pha đó merge**. Nếu hai pha làm song song, pha merge sau phải sửa lại `down_revision` trước khi merge. Orchestrator kiểm `alembic heads` ra đúng một head sau mỗi lần merge.

**Chế độ `DATA_SOURCE=file` sau mọi pha:** hành vi giữ nguyên. Mọi tính năng mới nằm sau `!IS_LOCAL` trong `lib/api.ts`; nhánh local vẫn gọi engine như cũ. Riêng B3 có một thay đổi cố ý: Vault không còn "độc lập với DATA_SOURCE" (D-B3a).

Phần B1 dưới đây là thiết kế chi tiết. B2-B4 ở mục 9-11 viết gọn hơn, đủ để User duyệt hướng; mỗi pha sẽ được viết chi tiết thêm trước khi giao nếu User yêu cầu.

---

# PHA B1: Nhập thực thể (chi tiết)

## 2. Bối cảnh & phạm vi B1

**Vấn đề.** Dữ liệu thật nằm ở `data/builder-data.json`. Hiện không có đường nào đưa nó vào Postgres đúng cách: `actions-import.ts` chặn ở chế độ api; nhánh api của `transfer.importJson` (POST từng bản ghi) hỏng ngay với file thật, làm mất field, nhân đôi khi chạy lại và vướng rate limit (Phụ lục A, mục 2).

```mermaid
sequenceDiagram
    actor U as User
    participant C as CoreImportPanel (client)
    participant SA as Server Action
    participant Core as FastAPI /api/v1/import
    participant DB as Postgres

    U->>C: chọn file, bấm "Kiểm tra"
    C->>SA: importToCoreAction(file, dry_run=1)
    SA->>Core: POST /import/datafile?dry_run=true (X-API-Key, qua lib/api.ts)
    Core->>DB: BEGIN, advisory lock, validate, lập kế hoạch, INSERT/UPDATE, flush
    Core->>DB: ROLLBACK
    Core-->>C: ImportReport (sẽ tạo N, sẽ GHI ĐÈ M kèm diff, K bản cũ hơn DB)
    U->>C: đọc diff, tích xác nhận, bấm "Nhập thật"
    C->>SA: importToCoreAction(file, dry_run=0, expect_replaced=M)
    SA->>Core: POST /import/datafile?dry_run=false&expect_replaced=M
    Core->>DB: BEGIN, lock, như trên; số ghi đè thực tế khác M thì ROLLBACK
    Core->>DB: ghi import_runs + import_audit + task_events, COMMIT
    Core-->>C: ImportReport (committed=true, import_id)
```

**In-scope B1**
- Backend: schema Pydantic cho file nhập; service nhập (chuẩn hoá, ánh xạ id, khớp bản ghi, diff, replace, dry-run, transaction, khoá tuần tự); bảng audit; hai endpoint `POST /api/v1/import/datafile`, `POST /api/v1/import/ai-logs`; pytest.
- Web ở `DATA_SOURCE=api`: panel "Chuyển dữ liệu JSON vào Postgres" ở `/data` (Kiểm tra → xem diff → xác nhận → Nhập thật); `LocalOnlyNotice` cho thành phần chỉ chạy ở chế độ file (cho tới khi B2-B4 thay thế chúng).

**Out-of-scope B1**
- Xoá bản ghi DB không có trong file, hay bất kỳ chế độ xoá hàng loạt nào. Không có.
- `meta.*`, `sync_urls` (B2), Vault, Chrome (B3), Jira (B4). B1 chỉ báo trong `ignored_fields`.
- Nhập CSV ở chế độ api (giữ đường cũ, hạn chế đã biết: rate limit).
- `scripts/smoke-test.sh` (cần Docker).

## 3. Thay đổi dữ liệu B1

| Bảng | Thay đổi | Index/Constraint | Ghi chú migration (downgrade?) |
|---|---|---|---|
| `import_runs` (mới) | `id uuid PK` (= `import_id`), `kind varchar(32)` (`datafile`/`ai_logs`), `file_sha256 char(64)`, `schema_version int`, `counts jsonb`, `actor varchar(100)`, `created_at timestamptz default now()` | CHECK `kind IN ('datafile','ai_logs')`; index `created_at` | Chỉ ghi khi `committed=true`. Dry-run không để lại dòng nào. |
| `import_audit` (mới) | `id uuid PK`, `import_id uuid FK → import_runs ON DELETE CASCADE`, `entity varchar(32)`, `entity_id uuid`, `action varchar(16)`, `before jsonb NULL`, `changed_fields text[]`, `created_at timestamptz default now()` | CHECK `entity IN ('project','task','task_event','note','ai_log')`, CHECK `action IN ('created','replaced')`; index `(import_id)`, `(entity, entity_id)` | `before` = toàn bộ giá trị cột của bản ghi **trước khi ghi đè** (null khi `created`). Không FK tới bảng nghiệp vụ, để audit còn khi bản ghi bị xoá. |
| `tasks`, `projects`, `notes`, `task_events`, `ai_logs` | Không đổi | Dùng sẵn PK, `projects.key` unique, partial unique `(source, external_id) WHERE deleted_at IS NULL`, các CHECK | — |

- File mới `apps/core/migrations/versions/<rev>_add_import_audit.py`, `down_revision = "d4e9f2a6b8c5"`. Không có Docker nên viết tay theo mẫu `d4e9f2a6b8c5_add_notes_archived_at.py`, hoặc `alembic revision --autogenerate` trên DB `_test` rồi dọn lại tay.
- Model mới `apps/core/app/models/import_audit.py` (`ImportRun`, `ImportAudit`), đăng ký trong `models/__init__.py`. Enum `kind/entity/action` dùng `enum_column()` (VARCHAR + CHECK) để `alembic check` không báo drift.
- `downgrade`: drop hai bảng. Mất lịch sử nhập và khả năng hoàn tác theo `before`; dữ liệu nghiệp vụ không bị ảnh hưởng.
- `conftest.py` phải thêm `import_audit, import_runs` vào câu `TRUNCATE` (backend-dev sửa).

**Rollback một lần nhập** (orchestrator ghi vào docs kèm SQL):
1. Bắt buộc trước lần nhập thật đầu tiên: `pg_dump`.
2. Hoàn tác theo `import_id` trong một transaction: với `action='replaced'` thì ghi lại cột từ `before`; với `action='created'` thì xoá bản ghi theo `entity_id` (task trước, rồi note, rồi project). Script hoàn tác **không** nằm trong phạm vi B1; B1 chỉ đảm bảo đủ dữ liệu để làm.

### 3.1. Ánh xạ thực thể

Ký hiệu: **G** giữ nguyên, **C** chuẩn hoá (có cảnh báo), **B** bỏ (báo trong `ignored_fields`).

**Project** (`projects[]` → `projects`)

| Field JSON | Cột | Xử lý |
|---|---|---|
| `id` (UUID v4) | `id` | G (D2) |
| `key` | `key` varchar(20) unique, regex `^[A-Z][A-Z0-9_]{1,19}$` | C (D7): bỏ dấu (NFKD, `Đ/đ`→`D`), in hoa, ký tự ngoài `A-Z0-9` → `_`, gộp `_`, cắt `_` hai đầu, tối đa 20 ký tự, không bắt đầu bằng chữ thì thêm `P_`, dưới 2 ký tự thì lỗi. File thật: `ONE NEXUS`→`ONE_NEXUS`, `SAO MỘC`→`SAO_MOC`, `KHÁC`→`KHAC`. Hai project trong file ra cùng key → lỗi. |
| `name`, `description` | cùng tên | G |
| `color` | varchar(7) hex | C (D7): hex → chữ thường; `hsl(h, s%, l%)` → `#rrggbb`; dạng khác → `null`. File thật: 14/14 là hsl. |
| `is_archived`, `created_at`, `updated_at` | cùng tên | G |

**Task** (`tasks[]` → `tasks`)

| Field JSON | Cột | Xử lý |
|---|---|---|
| `id` | `id` | G |
| `title` (≤500), `description`, `assignee` (≤200), `status`, `priority` | cùng tên | G, validate như `TaskBase` |
| `project_id` | `project_id` | Qua `project_id_map` (2.2); không có thì khớp `project.key` đã chuẩn hoá; vẫn không thấy → `null` + cảnh báo `project_unlinked` |
| `project` (object nhúng), `is_overdue`, `days_until_purge` | — | B |
| `due_at`, `completed_at` | timestamptz | G; datetime không có múi giờ → coi là UTC + cảnh báo |
| `scheduled_for` | date | G |
| `estimate_minutes` | CHECK `> 0`, ≤ 43200 | G; vi phạm → `null` + cảnh báo |
| `spent_minutes` | CHECK `>= 0` | G |
| `tags` | `varchar(64)[]` | `normalize_tags()`; > 20 tag → lỗi |
| `source`, `external_id`, `external_url` | cùng tên | G |
| `created_at`, `updated_at` | cùng tên | G, ghi tường minh (D13) |
| `deleted_at` khác null | — | Bỏ qua cả task, `skipped_trash` (D5). **Không** xoá bản tương ứng trong DB. |
| `events[]` | `task_events` | Xem dưới |
| `raw_payload` | `raw_payload` | Không nhận từ file (D11). Khi replace: **giữ nguyên** giá trị `raw_payload` đang có trong DB, không ghi `NULL` đè lên. |
| `status=done` mà `completed_at=null` | `completed_at` | = `updated_at` + cảnh báo |

**TaskEvent** (`tasks[].events[]`): `id` G; `task_id` = id task đích sau ánh xạ; `event_type` thuộc `TaskEventType` (sai → lỗi); `actor` ≤100; `payload` dict/null qua `_jsonable`, tối đa 16 KB; `created_at` G. Chỉ **chèn** event có id chưa tồn tại; event đã có thì không sửa, không xoá (task_events là audit trail).

**Note** (`notes[]`): `id`, `title` ≤300, `kind`, `content` ≤20000, `description`, `context` ≤200, `tags`, `is_pinned`, `is_dangerous`, `use_count` ≥0, `last_used_at`, `source`, `external_id`, `archived_at` (thiếu → null), `created_at`, `updated_at`: G. `project_id` ánh xạ như task. `deleted_at` khác null → `skipped_trash`. `raw_payload` như task.

**AiLog** (`ai-logs.json` → `ai_logs`, endpoint riêng): `id` G; `category` C (D9): hạ chữ thường, `UI/UX`→`web`, giá trị lạ (`DOCS`...) → `other`; `prompt`, `response` G, không rỗng; `handling` thiếu → `"(không ghi nhận)"` (để `AiLogRead` không vỡ); `created_at` G; `updated_at` thiếu → `created_at`.

**Mất dữ liệu có chủ đích ở B1:** object `project` nhúng, field tính toán, bản ghi đang ở thùng rác của file. `meta.*` và `sync_urls` chuyển ở B2. Không có field nghiệp vụ nào của project/task/note bị mất.

### 3.2. "Đã tồn tại" nghĩa là gì, và replace làm gì (D3 + D4)

**Bước 1: tìm bản ghi đích trong DB**, theo đúng thứ tự, dừng ở khoá đầu tiên khớp:

| Thực thể | Khoá 1 | Khoá 2 | Khi khớp bằng khoá 2 |
|---|---|---|---|
| Project | `id` | `key` đã chuẩn hoá | Ghi đè vào bản ghi DB (giữ **id của DB**); `project_id_map[file_id] = db_id` để task/note trỏ đúng. |
| Task | `id` (kể cả bản đang ở thùng rác DB) | `(source, external_id)`, `external_id` khác null, bản DB `deleted_at IS NULL` | Ghi đè vào bản DB, giữ id DB; event của task trong file gắn vào id DB. |
| Note | như Task | như Task | như Task |
| TaskEvent, AiLog | `id` | — | — |

Báo cáo ghi rõ `matched_by: "id" | "natural_key"` cho từng bản ghi bị ghi đè.

**Bước 2: quyết định**

| Tình huống | Hành động | Đếm vào |
|---|---|---|
| Không khớp | INSERT, audit `created` | `created` |
| Khớp, bản DB đang ở thùng rác (`deleted_at` khác null) | Không đụng, không hồi sinh | `skipped_trash_in_db` + cảnh báo |
| Khớp, so sánh không có khác biệt | Không ghi gì, không event, không audit | `unchanged` |
| Khớp, có khác biệt | UPDATE toàn bộ field nhập được bằng giá trị trong file; audit `replaced` với `before` + `changed_fields`; task thì thêm event | `replaced` (và `replaced_older` nếu file cũ hơn DB) |
| Bản ghi trong file đang ở thùng rác | Bỏ qua, không xoá gì trong DB | `skipped_trash` |

**So sánh "có khác biệt"** thực hiện **sau** chuẩn hoá (key, màu, tag, datetime so theo thời điểm UTC), trên các field nhập được, **trừ** `updated_at`, `created_at` và `raw_payload`. Nhờ vậy chạy lại cùng file lần hai ra `created = 0`, `replaced = 0`, toàn bộ là `unchanged` (tiêu chí idempotent).

**Khi ghi đè:**
- `updated_at` đặt bằng giá trị trong file (D13), ghi tường minh để `onupdate=func.now()` không đè. `created_at` giữ giá trị DB.
- `projects.key` được đổi theo file nếu khác; trùng với project khác trong DB → lỗi.
- Đổi `(source, external_id)` của task/note mà trùng với một bản ghi còn sống khác trong DB → lỗi (kiểm ở bước lập kế hoạch, `flush` bắt lần nữa).
- **Task:** thêm một event `updated`, actor `import:datafile`, payload `{"import_id", "changes": {field: {"old", "new"}}}` (giá trị qua `_jsonable`, chuỗi cắt 200 ký tự). Task tạo mới vẫn có event `synced`, actor `import:datafile`, payload `{"import_id", "schema_version"}` (D8).
- **Project, Note, AiLog** không có bảng event, nên dấu vết nằm ở `import_audit`.

**Rủi ro chính của replace: file cũ ghi đè trạng thái mới hơn trong Postgres.** Ví dụ: sau khi chuyển sang chế độ api, task được cập nhật qua API (đổi status, log time), rồi User nhập lại một bản export cũ. Rào chắn:
1. `dry_run` mặc định `true`.
2. Báo cáo liệt kê **từng** bản ghi sẽ bị ghi đè với diff field-by-field, và đánh dấu `file_older_than_db = true` khi `updated_at` trong file < `updated_at` trong DB. Có tổng `replaced_older`.
3. Commit phải gửi `expect_replaced=<số bản ghi sẽ bị ghi đè từ báo cáo dry-run>`. Nếu số thực tế lúc commit khác (DB đã thay đổi sau dry-run) → rollback, `committed=false`, lỗi `replace_count_mismatch`.
4. UI chặn nút Nhập thật cho tới khi tích xác nhận (4.5); có `replaced_older > 0` thì phải tích thêm một xác nhận riêng.
5. `import_audit.before` giữ giá trị cũ để hoàn tác.

### 3.3. Transaction, dry-run, giới hạn

- **All-or-nothing (D6).** Một request = một transaction; có lỗi nào → không ghi gì, `committed=false`.
- **Dry-run** mặc định `true`, chạy đúng đường code của lần ghi thật (validate, lập kế hoạch, INSERT/UPDATE, `flush` để bắt CHECK/unique của Postgres), rồi `ROLLBACK`. Không ghi `import_runs`/`import_audit`.
- **Khoá tuần tự:** `pg_try_advisory_xact_lock(hashtext('builder:import'))`; không lấy được → 409.
- **Batch:** đọc bản ghi đã có bằng `WHERE id = ANY(:ids)` theo lô 1000 (đọc đủ cột để diff); INSERT theo lô 500 dòng. UPDATE từng dòng bằng ORM vì mỗi dòng đổi một tập field khác nhau; ở quy mô vài nghìn dòng điều này chấp nhận được. Thứ tự: projects → tasks → task_events → notes → audit.
- **Giới hạn (D12):** body 10 MB (413); file ở web 8 MB; tối đa 1 000 project, 20 000 task, 10 000 note, 200 000 event, 20 000 ai_log (422); `schema_version` 1..4; `issues` tối đa 500; `replacements` tối đa 5 000 bản ghi, mỗi bản ghi tối đa 30 field, chuỗi cắt 200 ký tự (`replacements_truncated`). Trường hợp bị cắt thì các con số đếm vẫn đúng.

## 4. API contract B1

Router mới `app/api/v1/imports.py`, prefix `/import`, gắn vào `api_router` nên có sẵn `require_api_key`.

| Method | Path | Request | Response | Lỗi |
|---|---|---|---|---|
| POST | `/import/datafile` | Query: `dry_run: bool = true`, `expect_replaced: int \| None` (bắt buộc khi `dry_run=false`, ≥ 0). Body: `DataFileEnvelope` | 200 `ImportReport` | 401; 409 đang có lần nhập khác; 413 > 10 MB; 422 envelope sai, `schema_version` > 4, vượt số lượng, `dry_run=false` mà thiếu `expect_replaced` |
| POST | `/import/ai-logs` | Query: như trên. Body: `AiLogsEnvelope` | 200 `ImportReport` | như trên |

Lỗi ở mức dòng (enum sai, trùng khoá, lệch `expect_replaced`...) trả **200** với `committed=false`, vì `coreFetch` chỉ đọc `detail` khi status không OK, trả lỗi HTTP sẽ làm mất báo cáo. Các mảng trong envelope khai `list[dict]`; service validate từng dòng để gom lỗi theo `entity/index/id`.

```python
SUPPORTED_DATAFILE_VERSION = 4

class DataFileEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")   # khoá lạ ở cấp file → ignored_fields["file"]
    schema_version: int = Field(default=1, ge=1, le=SUPPORTED_DATAFILE_VERSION)
    exported_at: str | None = None
    projects: list[dict[str, Any]] = Field(max_length=1_000)
    tasks: list[dict[str, Any]] = Field(max_length=20_000)
    notes: list[dict[str, Any]] = Field(default_factory=list, max_length=10_000)
    meta: dict[str, Any] | None = None          # B1: chỉ báo bỏ qua. B2: nhập current_users.

class AiLogsEnvelope(BaseModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    exported_at: str | None = None
    ai_logs: list[dict[str, Any]] = Field(max_length=20_000)

# Schema từng dòng: ImportProject, ImportTask, ImportTaskEvent, ImportNote, ImportAiLog
# (field như bảng 3.1, extra="ignore"; service so khoá thô với model_fields để liệt kê
# ignored_fields). KHÔNG có field raw_payload.

class EntityCounts(BaseModel):
    received: int = 0
    created: int = 0
    replaced: int = 0
    replaced_older: int = 0         # trong số replaced, file cũ hơn DB
    unchanged: int = 0
    skipped_trash: int = 0          # đang ở thùng rác trong file
    skipped_trash_in_db: int = 0    # khớp với bản ghi đang ở thùng rác DB
    invalid: int = 0

class FieldChange(BaseModel):
    field: str
    old: Any                        # chuỗi cắt 200 ký tự
    new: Any

class Replacement(BaseModel):
    entity: Literal["project", "task", "note", "ai_log"]
    id: uuid.UUID                   # id trong DB
    file_id: uuid.UUID              # id trong file (khác id khi matched_by=natural_key)
    label: str                      # key project / title task, note / prompt ai_log, cắt 80 ký tự
    matched_by: Literal["id", "natural_key"]
    file_older_than_db: bool
    changes: list[FieldChange]

class ImportIssue(BaseModel):
    level: Literal["error", "warning"]
    entity: Literal["file", "project", "task", "task_event", "note", "ai_log"]
    index: int | None
    id: str | None
    code: str     # invalid_enum, key_normalized, color_converted, duplicate_external_id,
                  # natural_key_conflict, replace_count_mismatch, ...
    message: str  # tiếng Việt; không chép nội dung note

class KeyChange(BaseModel):
    original: str
    normalized: str

class ImportReport(BaseModel):
    import_id: uuid.UUID
    dry_run: bool
    committed: bool
    schema_version: int
    counts: dict[str, EntityCounts]   # projects, tasks, task_events, notes, ai_logs
    errors: int
    warnings: int
    issues: list[ImportIssue]
    issues_truncated: bool
    replacements: list[Replacement]
    replacements_truncated: bool
    project_key_changes: list[KeyChange]
    ignored_fields: dict[str, list[str]]
```

Service `app/services/import_service.py`: hàm thuần `normalize_project_key`, `normalize_color`, `map_ai_log_category`, `diff_fields(db_row, file_row, fields) -> list[FieldChange]` (unit test được, không cần DB); `import_datafile(session, envelope, *, dry_run, expect_replaced, file_sha256, actor="import:datafile")`; `import_ai_logs(...)`. Endpoint tính `file_sha256` từ body thô. Log một dòng tổng kết (đếm, `import_id`), không log nội dung. Docstring có banner cảnh báo: endpoint GHI ĐÈ bản ghi đã tồn tại, KHÔNG xoá, không nhận `raw_payload`, payload và nội dung note là dữ liệu không đáng tin.

## 5. Thay đổi Web B1

- **`lib/api.ts`**: `importDataFile(text, { dryRun, expectReplaced? })`, `importAiLogsFile(text, { dryRun, expectReplaced? })` → `coreFetch` POST, body là nguyên văn file (bỏ BOM nếu có). Ở `IS_LOCAL` thì reject `CoreApiError(..., 501)`.
- **`lib/types.ts`**: alias `ImportReport`, `Replacement`, `FieldChange`, `EntityCounts`, `ImportIssue` từ `lib/generated/openapi.d.ts`.
- **`app/actions.ts`**: `importToCoreAction(formData)` nhận `file`, `kind` (`datafile`/`ai-logs`), `dry_run` (mặc định `"1"`), `expect_replaced`. Kiểm kích thước ≤ `MAX_UPLOAD_BYTES`, giá trị hợp lệ. Chỉ `revalidateAll()` khi `committed`.
- **`lib/store/transfer.ts`**: ở chế độ api, `importJson` và `importAiLogsJson` ném lỗi "Dùng mục 'Chuyển dữ liệu JSON vào Postgres'". Nhánh file/memory và CSV giữ nguyên.
- **`components/core-import-panel.tsx`** (mới, client):
  - Chọn loại file → **Kiểm tra** → bảng đếm theo thực thể (nhận / tạo mới / **ghi đè** / không đổi / thùng rác / lỗi), danh sách đổi key project, issue (lỗi trước cảnh báo, tối đa 50 dòng, còn lại thu gọn).
  - **Khi `replaced > 0`: khung cảnh báo đỏ, đặt trên mọi thứ khác**: "N bản ghi trong Postgres sẽ bị GHI ĐÈ bằng nội dung file." Bên dưới là danh sách bản ghi bị ghi đè (nhóm theo thực thể, gập/mở được, mỗi dòng có bảng `field | hiện tại | sau khi nhập`), bản ghi nào `file_older_than_db` thì có nhãn "File cũ hơn dữ liệu hiện tại".
  - Khi `replaced_older > 0`: thêm dòng đậm "M bản ghi trong file CŨ HƠN dữ liệu đang có: nhập sẽ làm mất thay đổi gần đây (ví dụ trạng thái task đã cập nhật qua API)".
  - Nút **Nhập thật** chỉ bật khi: lần Kiểm tra gần nhất là cùng file (`name + size + lastModified`), `errors === 0`, và nếu `replaced > 0` thì đã tích "Tôi đã xem danh sách và đồng ý ghi đè N bản ghi"; nếu `replaced_older > 0` thì tích thêm "Tôi chấp nhận ghi đè M bản ghi mới hơn bằng dữ liệu cũ". Gửi kèm `expect_replaced = report.counts.*.replaced` (tổng).
  - Kết quả `replace_count_mismatch` → thông báo "Dữ liệu trong Postgres đã thay đổi sau lần Kiểm tra, hãy Kiểm tra lại".
  - Sau khi nhập: hiện `import_id`, nhắc "Kiểm tra lại sẽ thấy 0 tạo mới, 0 ghi đè". Nhắc chạy `pg_dump` trước lần nhập đầu tiên.
  - Render bằng text node, không `dangerouslySetInnerHTML`.
- **`components/local-only-notice.tsx`** (mới): hộp thông báo một dòng, prop `feature`.
- **`app/data/page.tsx`**, khi `!IS_LOCAL`: hiện `CoreImportPanel`; `DataImport` chỉ còn các loại CSV (prop mới `kinds` ở `components/data-import.tsx`); `RestoreJsonManager`, `FileUploadManager`, `JiraSyncManager`, `UrlSyncManager`, `CurrentUserManager` được thay bằng `LocalOnlyNotice` cho tới khi B2/B4 đưa bản api vào. Khi `IS_LOCAL`: không đổi gì, chỉ thêm các bước chuyển sang Postgres vào khối "Hướng dẫn đổi nguồn dữ liệu".
- `components/data-tabs.tsx` chưa tồn tại (Phụ lục A, mục 1). Nếu nhánh khác tạo nó trước, frontend-dev áp dụng cùng thay đổi vào đó và báo orchestrator.

## 6. Ownership B1

**backend-dev** (`apps/core/**`):
- `app/models/import_audit.py` (mới), `app/models/__init__.py`
- `app/models/enums.py` (thêm `ImportKind`, `ImportEntity`, `ImportAction`)
- `migrations/versions/<rev>_add_import_audit.py` (mới)
- `app/schemas/imports.py`, `app/services/import_service.py`, `app/api/v1/imports.py` (mới)
- `app/api/v1/router.py` (một dòng)
- `tests/conftest.py` (thêm hai bảng vào `TRUNCATE`)
- `tests/test_import_unit.py`, `tests/test_import_service.py`, `tests/test_import_api.py` (mới)
- `tests/fixtures/datafile_sample.json`, `tests/fixtures/ai_logs_sample.json` (mới, **dữ liệu tổng hợp**, không chép dữ liệu thật)

**orchestrator**: sinh lại `apps/web/lib/generated/openapi.d.ts` (`app.openapi()` + `npx openapi-typescript`, như `note-archive.md` mục 5); docs (`API_REFERENCE.md`, `AI_HANDOFF_STATE.md`, hướng dẫn chuyển đổi + SQL hoàn tác theo `import_id`, `ai_logs.md`, `lib/docs.ts`); sửa comment sai ở `lib/store/types.ts` (Phụ lục A, mục 3).

**frontend-dev** (`apps/web/**` trừ `lib/generated/**`): `lib/api.ts`, `lib/types.ts`, `app/actions.ts`, `lib/store/transfer.ts` (chỉ hai nhánh api), `app/data/page.tsx`, `components/data-import.tsx` (prop `kinds`), `components/core-import-panel.tsx`, `components/local-only-notice.tsx` (mới).

**Không ai sửa:** `data/**`, `lib/store/engine.ts`, `json-file.ts`, `csv.ts`, `app/actions-import.ts`, `app/jira-actions.ts`, các `*-manager.tsx`, `scripts/smoke-test.sh`, model nghiệp vụ hiện có.

Thứ tự: backend-dev → orchestrator sinh types → frontend-dev (song song được trong hai worktree; `tsc` web chỉ có nghĩa sau khi sinh types).

## 7. Tiêu chí nghiệm thu B1 (không cần Docker)

`TEST_DATABASE_URL=postgresql+asyncpg://<user>:<pass>@localhost:5432/<tên>_test`. Lệnh chạy trong `apps/core/`. Không có Postgres local thì test `db` bị skip, **không tính là pass**.

**Backend**
- [ ] `uv run ruff check app migrations tests` và `uv run ruff format --check app migrations tests` → exit 0.
- [ ] `uv run alembic heads` → một head, là revision mới, `down_revision = "d4e9f2a6b8c5"`.
- [ ] `export DATABASE_URL=$TEST_DATABASE_URL API_KEY=test-api-key-0123456789; uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic check` → cả bốn exit 0, "No new upgrade operations detected".
- [ ] `uv run pytest -q tests/test_import_unit.py` → pass: chuẩn hoá key (`ONE NEXUS`, `SAO MỘC`, `KHÁC`, `đường`→`DUONG`, `1ABC`→`P_1ABC`, chuỗi toàn ký tự đặc biệt → lỗi); `hsl(253, 70%, 65%)` → hex hợp lệ, `#2563EB` → `#2563eb`, `red` → `None`; category `TOOL`/`UI/UX`/`DOCS`; `diff_fields` bỏ qua `updated_at`, so datetime theo thời điểm UTC, so tag sau chuẩn hoá.
- [ ] `TEST_DATABASE_URL=… uv run pytest -q` → toàn bộ pass, không test `db` nào bị skip. Bắt buộc có:
  - Nhập fixture vào DB rỗng: id giữ nguyên, quan hệ project đúng, `created_at`/`completed_at`/`assignee`/`source`/`external_id`/`spent_minutes` giữ nguyên, task `done` thiếu `completed_at` được backfill, event chèn với id gốc, mỗi task mới có event `synced` mang `import_id`, `import_runs` có 1 dòng, `import_audit` có `created` cho từng bản ghi.
  - **Idempotent:** nhập lại cùng fixture → mọi thực thể `created == 0`, `replaced == 0`; số dòng mọi bảng nghiệp vụ không đổi; không thêm event.
  - **Replace:** sửa `status` và `title` của một task trong DB qua API, nhập lại fixture → task đó `replaced == 1`, `changes` có đúng `status` và `title`, giá trị cột trở về như file, `updated_at` bằng giá trị trong file, có event `updated` với `changes`, `import_audit.before` chứa giá trị trước khi ghi đè, `file_older_than_db == true`, `replaced_older == 1`.
  - Replace giữ nguyên `raw_payload` đang có trong DB.
  - Khớp theo khoá tự nhiên: project cùng key khác id → ghi đè vào project DB, không tạo mới, task trong file trỏ về id DB; task khác id nhưng cùng `(source, external_id)` còn sống → ghi đè vào task DB, `matched_by == "natural_key"`.
  - Bản DB đang ở thùng rác → `skipped_trash_in_db`, `deleted_at` không đổi, không ghi đè. Bản trong file ở thùng rác → `skipped_trash`, bản DB tương ứng còn nguyên.
  - Không xoá: DB có bản ghi không có trong file → vẫn còn sau khi nhập.
  - **Dry-run:** đếm dòng mọi bảng (cả `import_runs`, `import_audit`, `task_events`) không đổi; `counts` và `replacements` của dry-run giống lần ghi thật.
  - **`expect_replaced`:** dry-run báo `replaced=1`; sửa thêm một task trong DB; commit với `expect_replaced=1` → `committed=false`, lỗi `replace_count_mismatch`, DB không đổi. Commit thiếu `expect_replaced` → 422.
  - **All-or-nothing:** một task enum sai ở cuối fixture → `committed=false`, không bảng nào đổi.
  - Hai task còn sống trong file cùng `(jira, X-1)` → lỗi `duplicate_external_id`. Ghi đè làm `(source, external_id)` trùng với bản ghi còn sống khác → lỗi `natural_key_conflict`.
  - `raw_payload` trong file bị bỏ và nằm trong `ignored_fields["task"]`.
  - `ai_logs`: `handling` thiếu → `"(không ghi nhận)"`, sau đó `GET /api/v1/ai-logs` trả 200.
  - API: thiếu key → 401; `schema_version: 99` → 422; body không phải object → 422; `Content-Length` > 10 MB → 413; không truyền `dry_run` → DB không đổi; giữ advisory lock ở session khác → 409.
- [ ] **File thật, chỉ đọc** (skip khi thiếu biến):
  ```bash
  IMPORT_REAL_DATAFILE=/Users/hungdv-mac/Downloads/ai_assistant_personal/data/builder-data.json \
  IMPORT_REAL_AILOGS=/Users/hungdv-mac/Downloads/ai_assistant_personal/data/ai-logs.json \
  TEST_DATABASE_URL=… uv run pytest -q -s -k real_file
  ```
  Mở file bằng `"rb"`, assert sha256 và `mtime` không đổi trước/sau. Kỳ vọng (số liệu ngày 2026-10-07): dry-run trên DB rỗng `errors == 0`, `projects.received == 14`, `tasks.received == 498`, `notes.received == 0`, 3 `project_key_changes`, 14 cảnh báo đổi màu, `replaced == 0`; ghi thật: `created` 14/498; chạy lại: `created == 0`, `replaced == 0`, `unchanged` 14/498; ai-logs: `received == 61`, `errors == 0`. Có lỗi trên file thật thì **dừng, báo User**, không sửa file.

**Types (orchestrator)**: `openapi.d.ts` có hai path mới và schema `ImportReport`, `Replacement`; `git diff --stat` chỉ chứa phần liên quan.

**Web**
- [ ] `cd apps/web && npx tsc --noEmit` → exit 0.
- [ ] `git diff --name-only <base>...HEAD -- apps/web/lib/generated apps/web/lib/store/engine.ts apps/web/lib/store/json-file.ts apps/web/app/actions-import.ts` → rỗng.
- [ ] `grep -n "store/engine\|dangerouslySetInnerHTML" apps/web/components/core-import-panel.tsx apps/web/components/local-only-notice.tsx` → rỗng.
- [ ] `grep -rn "CORE_API_KEY\|X-API-Key" apps/web/components/` → rỗng.

**Kịch bản tay (UAT)**
1. `pg_dump`. `make use-db`. Mở `/data`: thành phần chỉ-file hiện `LocalOnlyNotice`.
2. Kiểm tra `builder-data.json` → 14 project / 498 task tạo mới, 0 ghi đè, không có khung đỏ. Nhập thật.
3. `/tasks`, `/stats`: "hoàn thành 7 ngày" phản ánh ngày đóng thật.
4. Đổi trạng thái một task trên web (api). Kiểm tra lại cùng file → khung đỏ "1 bản ghi sẽ bị GHI ĐÈ", diff `status`, nhãn "File cũ hơn". Nút Nhập thật khoá cho tới khi tích đủ hai ô.
5. Sau khi Kiểm tra, đổi thêm một task rồi bấm Nhập thật → thông báo "đã thay đổi sau lần Kiểm tra".
6. Không có Docker: `curl -X POST -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" --data-binary @/Users/hungdv-mac/Downloads/ai_assistant_personal/data/builder-data.json "http://localhost:8000/api/v1/import/datafile?dry_run=true"` (curl chỉ đọc file).

**Review**: `db-reviewer` (migration audit, batch, advisory lock), `code-reviewer`, **`security-auditor`** (endpoint ghi hàng loạt có ghi đè, Server Action mới, giới hạn kích thước).

## 8. Quyết định B1 (đã chốt) và rủi ro

| # | Quyết định | Trạng thái |
|---|---|---|
| D1 | Endpoint nhập hàng loạt ở core | Chốt |
| D2 | Giữ id UUID trong file | Chốt |
| D3 | Khớp theo `id`, sau đó khoá tự nhiên (bảng 3.2) | Chốt; làm rõ cho replace ở 3.2 |
| D4 | Bản ghi đã tồn tại → **replace**; bản giống hệt → `unchanged`; không xoá | Chốt (User) |
| D5 | Bỏ qua bản ghi ở thùng rác của file | Chốt |
| D6 | All-or-nothing, `dry_run` mặc định `true` | Chốt |
| D7 | Tự chuẩn hoá key, đổi hsl → hex, có cảnh báo | Chốt (User) |
| D8 | Task tạo mới có event `synced`, actor `import:datafile` | Chốt; v2 thêm event `updated` cho task bị ghi đè |
| D9 | ai_logs: endpoint riêng, `UI/UX`→`web`, lạ→`other`, `handling` thiếu → `"(không ghi nhận)"` | Chốt |
| D11 | Không nhận `raw_payload` từ file; khi replace giữ `raw_payload` của DB | Chốt; phần giữ DB là bổ sung v2 |
| D12 | Giới hạn như 3.3 | Chốt |
| D13 | Giữ timestamp gốc | Chốt |
| D14 | Bỏ qua field lạ, liệt kê trong báo cáo | Chốt |
| D15 | Thêm bảng `import_runs` / `import_audit` (migration) để lưu `before` khi ghi đè | **Mới, cần User duyệt** (hệ quả của D4: không có nó thì ghi đè không hoàn tác được ngoài `pg_dump`) |
| D16 | So sánh "có khác biệt" bỏ qua `updated_at`; khác mỗi `updated_at` → `unchanged`, không ghi | **Mới, cần User duyệt** |
| D17 | Commit bắt buộc gửi `expect_replaced` khớp với số thực tế | **Mới, cần User duyệt** |

Rủi ro B1:
- **File cũ ghi đè trạng thái mới hơn trong Postgres** (rủi ro lớn nhất của D4). Giảm thiểu: dry-run mặc định, diff từng bản ghi, cờ `file_older_than_db`, khung cảnh báo đỏ và hai ô xác nhận, `expect_replaced`, `import_audit.before`. Rủi ro còn lại: User tích xác nhận mà không đọc diff.
- **Web không có đăng nhập.** Ai mở được `/data` (kể cả qua LAN khi `make lan-up`) đều có thể ghi đè dữ liệu bằng một file tự soạn. Replace làm rủi ro này nặng hơn v1. Giảm thiểu hiện có: chỉ bind localhost; dấu vết ở `import_audit`. Cần ghi vào `AI_HANDOFF_STATE.md` như một hạn chế đã biết.
- **Lệch chuẩn hoá key giữa web và backend**: Jira sync ở chế độ file tạo key bằng `toUpperCase()` không bỏ dấu cách (`ONE NEXUS`), backend thành `ONE_NEXUS`. Nhập lại file sau khi tiếp tục dùng chế độ file vẫn khớp được (cùng hàm chuẩn hoá), nhưng hai nơi hiển thị key khác nhau. B4 sẽ dùng chung hàm chuẩn hoá ở backend.
- `WipeDataManager` ở chế độ api thao tác trên engine RAM, không chạm Postgres; dễ gây hiểu nhầm. Ngoài phạm vi.
- Lệch `openapi.d.ts` khi sinh ngoài container; không có smoke test.

---

# PHA B2: Cài đặt người dùng và sync_urls (gọn)

## 9. B2

**Mục tiêu.** Ở chế độ api, `getCurrentUsersApi()` và `getAssigneesApi()` trả `[]`, `getSyncUrlsApi()` trả `[]`, `setCurrentUsersApi()` là no-op. Hệ quả: trang `/team` không tách được task cá nhân/team, JQL mặc định của Jira sync không có người dùng. B2 đưa các cài đặt này vào Postgres.

**Dữ liệu**

| Bảng | Cột | Ghi chú |
|---|---|---|
| `app_settings` (mới) | `key varchar(64) PK`, `value jsonb NOT NULL`, `updated_at timestamptz` | Key-value cho cài đặt **không bí mật**. Key hợp lệ khai báo cứng trong code (`current_users`, `sync_urls`); key lạ bị từ chối. Không dùng bảng này cho token hay secret. Downgrade: drop bảng, mất cài đặt. |

**API** (prefix `/api/v1`)

| Method | Path | Request / Response | Ràng buộc |
|---|---|---|---|
| GET / PUT | `/settings/current-users` | `{ "names": list[str] }` | ≤ 20 tên, mỗi tên strip, 1..200 ký tự, loại trùng |
| GET / PUT | `/settings/sync-urls` | `{ "urls": list[str] }` | ≤ 50 URL, chỉ `https`, host thuộc allowlist (D-B2b) |
| GET | `/tasks/assignees` | `list[str]` | `DISTINCT assignee` trên task còn sống; khai báo **trước** `/tasks/{task_id}` |
| (mở rộng B1) | `/import/datafile` | `meta.current_users` → replace `current_users` nếu có trong file và khác giá trị DB; hiện trong `replacements` với `entity="setting"` | Thêm `"setting"` vào enum `ImportEntity` (migration nhỏ sửa CHECK, hoặc gộp vào migration B2) |

**`meta.minutes_logged_today/date`: đề xuất không lưu (D-B2a).** Ở chế độ api, backend đã tự tính `minutes_logged_today` từ event `time_logged` trong ngày (`task_service.get_stats`). Con số trong file chỉ là bộ đếm của riêng hôm nay, không gắn với task nào; muốn nhập phải bịa ra một event không có task. Báo cáo nhập sẽ ghi "bỏ qua: backend tự tính từ nhật ký".

**`sync_urls` trong file:** `engine.snapshot()` hiện không ghi `sync_urls` (Phụ lục A, mục 4), nên file thật không có. B2 sửa `snapshot()`/`restore()` để chế độ file lưu `sync_urls` (tăng `SCHEMA_VERSION` lên 5, kèm bước migrate backfill `[]`), rồi endpoint nhập đọc `sync_urls` nếu có. Thay đổi này **chạm chế độ file**: đây là sửa lỗi, không đổi hành vi cố ý.

**Chạy URL sync ở chế độ api** (fetch Excel rồi nhập task) cần endpoint upsert của B4, nên B2 chỉ lưu danh sách URL. Nút "Đồng bộ" ở chế độ api vẫn là `LocalOnlyNotice` cho tới B4.

**Web:** `lib/api.ts` (nhánh api cho 4 hàm trên), `CurrentUserManager`/`UrlSyncManager` hiện lại ở chế độ api (thay `LocalOnlyNotice`), `lib/store/engine.ts` + `json-file.ts` + `types.ts` (v5, `sync_urls`).

**Bảo mật:** `syncFromUrlAction` hiện fetch URL bất kỳ do người dùng nhập từ phía server (SSRF, `redirect: 'follow'`). B2 thêm kiểm tra `https` + allowlist host ở cả lúc lưu (backend) và lúc fetch (web, kiểm lại URL cuối sau redirect). Cần `security-auditor`.

**Ownership:** backend-dev: `models/app_setting.py`, migration `<rev>_add_app_settings.py`, `schemas/settings.py`, `services/settings_service.py`, `api/v1/settings.py`, `api/v1/tasks.py` (route `/assignees`), `router.py`, mở rộng `import_service.py`, test. frontend-dev: `lib/api.ts`, `lib/store/engine.ts`, `lib/store/json-file.ts`, `lib/store/types.ts`, `app/actions.ts` (allowlist), `app/data/page.tsx`, `components/current-user-manager.tsx`, `components/url-sync-manager.tsx`.

**Nghiệm thu:** ruff, `alembic heads/check` một head; pytest: PUT/GET round-trip, từ chối > 20 tên, URL `http://`, host ngoài allowlist, key lạ; `/tasks/assignees` không trả assignee của task trong thùng rác và không bị nuốt bởi `/{task_id}`; nhập `builder-data.json` → `current_users == ["Đoàn Việt Hưng"]`, chạy lại → `unchanged`. Web: `tsc`; file v4 cũ nạp lên được và có `sync_urls: []`; UAT: `/team` ở chế độ api tách đúng task cá nhân.

---

# PHA B3: Vault (ciphertext) và lịch sử Chrome (gọn)

## 10. B3

### 10.1. Vault

**Hiện trạng.** `lib/vault/store.ts` lưu blob đã mã hoá ở `data/vault.json`, **cố ý độc lập với `DATA_SOURCE`**. Mã hoá/giải mã ở trình duyệt (PBKDF2 600k vòng + AES-GCM, blob v1/v2 có `wraps.password`/`wraps.recovery`). Server chỉ thấy ciphertext. Chống ghi đè bằng `expectedUpdatedAt`.

**Đề xuất.** Khi `DATA_SOURCE=api`, blob nằm ở Postgres; khi `file`/`memory` thì giữ nguyên như hiện tại (D-B3a).

| Bảng | Cột | Ghi chú |
|---|---|---|
| `vault_blobs` (mới) | `id smallint PK CHECK (id = 1)` (một két duy nhất), `blob jsonb NOT NULL`, `blob_version smallint`, `updated_at timestamptz` (lấy từ blob) | Một dòng. |
| `vault_blob_history` (mới) | `id uuid PK`, `blob jsonb`, `replaced_at timestamptz` | Giữ **5 bản trước** mỗi lần ghi đè, để lỡ ghi đè vẫn khôi phục được (D-B3b). |

| Method | Path | Ghi chú |
|---|---|---|
| GET | `/api/v1/vault` | 200 blob, hoặc 404 khi chưa có |
| PUT | `/api/v1/vault` | Body `{ blob, expected_updated_at: str \| null }`; lệch → 409 (giữ đúng ngữ nghĩa `VaultConflictError`) |
| DELETE | `/api/v1/vault` | Xoá két (bản cũ vẫn vào history) |
| POST | `/api/v1/import/vault?dry_run=true` | Nhập nội dung `vault.json`. DB chưa có két → tạo. DB đã có két với `updated_at` khác → **replace** theo D4, nhưng dry-run báo rõ "Két hiện có sẽ bị thay; KHÔNG xem được nội dung để so sánh", và bản cũ vào `vault_blob_history`. |

**Ràng buộc zero-knowledge (bắt buộc, security-auditor kiểm):**
- Backend **không bao giờ** giải mã, không nhận mật khẩu hay recovery code, không có code import thư viện mã hoá cho Vault.
- Chỉ kiểm hình dạng blob (port `isVaultBlob`: `v ∈ {1,2}`, các field base64, `kdf.iterations ≥ 100 000`) và kích thước ≤ 5 MB.
- Không log blob, không đưa blob vào `import_audit.before` (chỉ ghi `updated_at` cũ/mới), không có trong export JSON chung của chế độ api.
- Diff ở dry-run chỉ so `updated_at`, `v`, kích thước.
- Web vẫn đi qua `lib/api.ts` (server-only) giống mọi route khác; trình duyệt nhận blob qua Server Action/route như hiện nay.

### 10.2. Lịch sử Chrome

**Hiện trạng.** `lib/chrome-history.ts` copy file SQLite `History` của Chrome trên **máy chạy web**, đọc bằng `sqlite3` CLI, ghi đè `data/chrome-history.json` (`{synced_at, source_path, items: [{url, title, visit_count, last_visit_time}]}`); `/history` đọc file đó trực tiếp. `last_visit_time` là giờ địa phương **không có múi giờ** (`'localtime'` trong SQL).

**Đề xuất.** Việc đọc Chrome **vẫn ở web** (backend chạy trong container, không thấy hồ sơ Chrome của host). Ở chế độ api, web đẩy kết quả lên core thay vì ghi file.

| Bảng | Cột | Index/Constraint |
|---|---|---|
| `browser_history` (mới) | `id uuid PK`, `profile varchar(200)` (tên thư mục profile, không lưu đường dẫn tuyệt đối), `url text`, `title text`, `visit_count int ≥ 0`, `last_visit_at timestamptz`, `synced_at timestamptz` | unique `(profile, url_hash)` với `url_hash = sha256(url)` (URL dài không index trực tiếp được); index `last_visit_at DESC` |

| Method | Path | Ghi chú |
|---|---|---|
| POST | `/api/v1/browser-history/batch` | `{ profile, items[] }`, ≤ 10 000 item mỗi lần, upsert theo `(profile, url_hash)`: lấy `visit_count` và `last_visit_at` lớn hơn |
| GET | `/api/v1/browser-history?q=&profile=&limit=50&offset=` | `Page[...]`, phân trang server-side (rule 3.5) |
| DELETE | `/api/v1/browser-history?profile=` | Xoá theo profile (thay cho xoá file) |
| POST | `/api/v1/import/browser-history?dry_run=true` | Nhập `chrome-history.json`: đổi `last_visit_time` từ giờ `display_timezone` sang UTC; upsert như trên (với dữ liệu này "replace" nghĩa là lấy số lớn hơn, không bao giờ giảm) |

**Bảo mật/riêng tư:**
- Lịch sử duyệt web là dữ liệu cá nhân nhạy cảm; URL có thể chứa token trong query string (link reset mật khẩu, OAuth `code=`). Đề xuất bỏ query string và fragment trước khi lưu (D-B3c).
- **Lỗi có sẵn cần sửa trong B3:** `scrapeChromeHistory` ghép `customPath` (do client gửi qua `syncChromeHistoryAction`) vào chuỗi lệnh shell `exec(\`sqlite3 -json "${tmpHistoryPath}" ...\`)`. `customPath` chỉ đi vào `fs.copyFileSync`, nhưng `limit` được nội suy vào SQL/shell và không được kiểm tra kiểu ở Server Action. Chuyển sang `execFile` với mảng tham số và ép `limit` về số nguyên trong khoảng 1..10 000; `customPath` phải nằm dưới thư mục Chrome của user.
- `security-auditor` bắt buộc cho cả 10.1 và 10.2.

**Ownership B3:** backend-dev: models `vault.py`, `browser_history.py`, migration `<rev>_add_vault_and_browser_history.py`, schemas/services/routers tương ứng, mở rộng `import_service.py` (hoặc service nhập riêng), test. frontend-dev: `lib/vault/store.ts` (rẽ nhánh theo `DATA_SOURCE`), `lib/api.ts`, `lib/chrome-history.ts`, `app/actions-chrome.ts`, `app/history/page.tsx`, `components/vault-import-manager.tsx`, `components/chrome-history-manager.tsx`, `components/core-import-panel.tsx` (thêm loại file vault/chrome). **Không ai sửa** `lib/vault/crypto.ts` (thuật toán mã hoá không đổi).

**Nghiệm thu B3:** pytest: PUT với `expected_updated_at` sai → 409; blob sai hình dạng/quá 5 MB → 422/413; ghi đè đẩy bản cũ vào history, giữ đúng 5 bản; `grep -rn "cryptography\|AESGCM\|pbkdf2" apps/core/app` không có kết quả liên quan vault; log của request vault không chứa `ciphertext`. Batch history upsert idempotent; giờ địa phương đổi đúng sang UTC; query string bị bỏ (nếu D-B3c chốt). Web: `tsc`; UAT: tạo két ở chế độ file → nhập lên api → mở khoá được bằng cùng mật khẩu và recovery code; `/history` phân trang 50/trang ở chế độ api.

---

# PHA B4: Jira sync ở backend (gọn)

## 11. B4

**Hiện trạng.**
- `syncJiraAction` chạy trong web, chỉ chế độ file. Nó gọi `POST {baseUrl}/rest/api/3/search/jql` (tối đa 100 trang × 100 issue), ánh xạ issue → task, tự tạo project theo key, chỉ chạy được trên engine.
- Cấu hình kết nối, **kể cả API token Jira**, nằm ở `localStorage` của trình duyệt dưới dạng chữ rõ (`jira-sync-manager.tsx`), và bị gửi kèm mỗi lần sync qua Server Action.
- JQL mặc định dùng `currentUsers` của engine.

**Đề xuất chia hai phần, merge độc lập:**

**B4a: upsert hàng loạt cho integration + lưu kết nối**

| Bảng | Cột | Ghi chú |
|---|---|---|
| `integration_connections` (mới) | `id uuid PK`, `kind varchar(32)` (`jira`), `name varchar(100)`, `base_url text` (chỉ `https`), `account_email varchar(200)`, `secret_ciphertext bytea`, `secret_last4 char(4)`, `config jsonb` (`jql`, `project_key`, `project_name`), `last_sync_at timestamptz`, `created_at`, `updated_at` | unique `(kind, name)` |

| Method | Path | Ghi chú |
|---|---|---|
| GET | `/api/v1/integrations` | Danh sách kết nối. **Không bao giờ trả token**, chỉ `has_secret` và `secret_last4`. |
| POST / PATCH / DELETE | `/api/v1/integrations[/{id}]` | Token chỉ ghi (write-only); PATCH không gửi token thì giữ token cũ. |
| POST | `/api/v1/tasks/upsert-batch` | `{ source, items: TaskUpsert[] ≤ 1 000 }`, upsert theo `(source, external_id)` còn sống; tạo project theo key qua **cùng hàm `normalize_project_key` của B1**; event `synced` (actor `integration:<name>`) khi tạo, `updated` kèm diff khi đổi; `raw_payload` lưu nhưng đánh dấu không đáng tin. Dùng chung cho Jira, URL sync và Excel import ở chế độ api. |

**Mã hoá token:** token phải giải mã được ở server (để gọi Jira), nên đây **không phải** zero-knowledge như Vault. Mã hoá khi lưu bằng khoá riêng `INTEGRATION_SECRET_KEY` (env, Fernet/AES-GCM, khác `API_KEY`); thiếu khoá thì endpoint tạo kết nối trả 503. Mất khoá thì phải nhập lại token. Không log, không đưa token vào `raw_payload`, `import_audit`, response hay message lỗi.

**Chuyển cấu hình từ trình duyệt:** panel B4 đọc `localStorage` (phía client) và có nút "Chuyển các kết nối này lên server" (gửi qua Server Action một lần, rồi xoá khỏi `localStorage` khi thành công). Đề xuất có nút này (D-B4c).

**B4b: chạy sync**
- `POST /api/v1/integrations/{id}/sync?since=` chạy sync theo yêu cầu, polling, không webhook (theo `project.md`). Trả `{added, updated, skipped, errors}`. Giới hạn 100 trang, timeout 30 giây mỗi request tới Jira, chỉ gọi tới `base_url` đã lưu (không theo redirect sang host khác).
- JQL mặc định dùng `current_users` của B2.
- Nơi chạy connector: xem D-B4a. `project.md` quy định connector viết bằng **TypeScript + MCP SDK** trong `mcp-servers/` (thư mục này chưa tồn tại). Viết connector Python trong `apps/core` là đi lệch quy ước đó.
- URL sync và Excel import ở chế độ api: web vẫn tải/đọc Excel như hiện tại, rồi gọi `upsert-batch` thay vì engine.
- Chế độ file: `syncJiraAction` giữ nguyên.

**Bảo mật:** lưu token phía server, outbound HTTP tới host do người dùng cấu hình (SSRF: chỉ `https`, chặn IP private/loopback trừ khi User cho phép Jira on-prem), dữ liệu Jira là untrusted (không bao giờ đưa vào prompt như instruction). `security-auditor` **bắt buộc**.

**Ownership B4:** backend-dev: models `integration.py`, migration `<rev>_add_integration_connections.py`, `core/secrets.py` (mã hoá token), schemas/services/routers integrations + `tasks.py` (`/upsert-batch` khai báo trước `/{task_id}`), connector (nếu D-B4a chọn Python), `pyproject.toml` (+ lock) nếu cần thư viện. frontend-dev: `lib/api.ts`, `app/jira-actions.ts` (nhánh api), `app/actions-import.ts` (nhánh api gọi upsert), `app/actions.ts` (`syncFromUrlAction` nhánh api), `components/jira-sync-manager.tsx`, `components/file-upload-manager.tsx`, `components/url-sync-manager.tsx`, `app/data/page.tsx`. orchestrator: `.env.example`, `docker-compose*.yml` (biến `INTEGRATION_SECRET_KEY`), docs.

**Nghiệm thu B4:** pytest: token không xuất hiện trong mọi response (`GET`, `POST`, lỗi), trong log (caplog), trong DB ở dạng chữ rõ; `upsert-batch` idempotent (chạy hai lần → `added=0`); trùng `(source, external_id)` với task trong thùng rác thì tạo mới (partial index); connector chạy với Jira giả (`httpx.MockTransport`), không gọi mạng thật; `base_url` `http://` hoặc `127.0.0.1` bị từ chối. Web: `tsc`; `grep -rn "localStorage" apps/web/components/jira-sync-manager.tsx` chỉ còn ở đường chuyển một lần. UAT: sync thật với Jira của User ở chế độ api, kết quả khớp số task đã nhập ở B1 (`updated`, không `added` trùng).

---

## 12. Câu hỏi còn lại cần User chốt

**B1**
- **D15:** Thêm bảng `import_runs` / `import_audit` (có migration) để lưu giá trị trước khi ghi đè, phục vụ hoàn tác? Đề xuất: có.
- **D16:** Bản ghi chỉ khác `updated_at` thì coi là không đổi, không ghi đè? Đề xuất: có.
- **D17:** Lần nhập thật bắt buộc gửi `expect_replaced` khớp với số bản ghi ghi đè thực tế, lệch thì huỷ? Đề xuất: có.

**B2**
- **D-B2a:** Không lưu `minutes_logged_today` (backend đã tự tính từ nhật ký)? Đề xuất: không lưu.
- **D-B2b:** Allowlist host cho `sync_urls`? Đề xuất: Google Drive/Sheets, SharePoint/OneDrive; thêm host khác qua biến môi trường.

**B3**
- **D-B3a:** Ở chế độ api, Vault chuyển vào Postgres? Việc này bỏ thiết kế hiện tại "Vault độc lập với DATA_SOURCE". Đề xuất: có.
- **D-B3b:** Nhập `vault.json` vào Postgres đã có két → replace, kèm giữ 5 bản cũ trong `vault_blob_history`? Hay từ chối khi đã có két? Đề xuất: replace có lịch sử.
- **D-B3c:** Bỏ query string và fragment của URL lịch sử Chrome trước khi lưu, để tránh lưu token? Đề xuất: bỏ.

**B4**
- **D-B4a:** Connector Jira chạy ở đâu?
  - (1) Python trong `apps/core`: lệch quy ước TS + MCP trong `project.md`.
  - (2) Giữ phần gọi Jira ở web (TS), token lưu ở core, web lấy token qua endpoint nội bộ: phức tạp, token đi qua hai tiến trình.
  - (3) Tạo `mcp-servers/jira` (TS): đúng quy ước nhưng thêm một service mới.
  - Đề xuất: (1), kèm ghi chú ngoại lệ vào `project.md`.
- **D-B4b:** Token Jira mã hoá bằng `INTEGRATION_SECRET_KEY` trong `.env` (mất khoá thì nhập lại token)? Đề xuất: có.
- **D-B4c:** Có nút chuyển cấu hình Jira từ `localStorage` lên server một lần? Đề xuất: có.
- **D-B4d:** Cho phép `base_url` Jira trỏ tới IP private (Jira on-prem trong LAN)? Đề xuất: mặc định chặn, mở bằng biến môi trường.

## Phụ lục A. Giả định ban đầu lệch với code thật

1. `components/data-tabs.tsx` và `LocalOnlyNotice` không tồn tại (grep toàn repo, kể cả `.next`). Trang `/data` là các khối `<details>` trong `app/data/page.tsx`.
2. `importDataAction` → `transfer.importJson` **có** nhánh api (POST từng bản ghi), nhưng với file thật nó hỏng như sau:
   - Màu `hsl(...)` → `ProjectCreate` 422 ngay project đầu tiên; vòng lặp project không có `try/catch` nên cả lần nhập dừng.
   - Key `ONE NEXUS`, `SAO MỘC`, `KHÁC` không qua regex.
   - Task không gửi `source`, `external_id`, `external_url`, `assignee`, `completed_at`, `created_at`, `spent_minutes`, `events`; `create_task` đặt `completed_at = now()` cho task `done`.
   - Task không có chống trùng.
   - 498+ request liên tiếp vượt rate limit 120 req/phút.
   - Ai-log: `category` in hoa và thiếu `handling` → 61/61 bị từ chối.
3. Comment ở `lib/store/types.ts` ("chỉ là POST từng bản ghi... không cần viết lớp chuyển đổi") và header `transfer.ts` ("chỉ cần đổi DATA_SOURCE=api rồi nhập lại") sai theo mục 2.
4. `engine.snapshot()` không ghi `sync_urls`, `restore()` không đọc nó, nên danh sách URL đồng bộ chỉ sống trong RAM. File thật chỉ có khoá `schema_version, exported_at, projects, tasks, notes, meta`. Sửa ở B2.
5. `ai_logs` nằm ở `data/ai-logs.json` riêng (từ schema v4), với schema khác backend.
6. Jira token nằm ở `localStorage` dưới dạng chữ rõ; `syncFromUrlAction` fetch URL bất kỳ phía server; `scrapeChromeHistory` dựng lệnh shell bằng nội suy chuỗi. Ba điểm này lần lượt được xử lý ở B4, B2, B3.
7. Số liệu file thật (2026-10-07):
   - `builder-data.json`: 14 project (14 màu hsl, 3 key không hợp lệ); 498 task, tất cả `source=jira` có `external_id`, không task nào ở thùng rác, không có event, không có `scheduled_for`/`estimate_minutes`/`spent_minutes > 0`; 0 note; `meta.current_users = ["Đoàn Việt Hưng"]`.
   - `ai-logs.json`: 61 log.
   - `chrome-history.json`: có `synced_at`, `source_path`, `items` với `last_visit_time` là giờ địa phương không có múi giờ.
