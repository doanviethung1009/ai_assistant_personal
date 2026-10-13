# Spec: Jira sync lọc theo assignee HOẶC reporter, và hiển thị reporter trên task

- Trạng thái: CHỐT (User duyệt R1-R9 theo đề xuất, 2026-10-10). Bắt đầu code sau khi epic auth được commit (R8).
- Tác giả: architect
- Ngày: 2026-10-10
- Nhánh lúc viết: `feat/auth-multiuser` (epic đăng nhập đa người dùng đang code dở, chưa commit)
- Alembic head lúc viết: `b2f7a9c1d4e6` (`add_users_and_ownership`, file chưa commit của epic auth). Không có migration nào khác trỏ `down_revision` vào nó.
- Phụ thuộc: xem R8. Migration của epic này nối sau head **tại thời điểm code**. backend-dev phải chạy `uv run alembic heads` trước khi đặt `down_revision`, không chép cứng giá trị trên.

## 1. Bối cảnh & phạm vi

### 1.1. Vấn đề

1. **Lọc.** Ô "Theo người" hiện chỉ lọc theo người được giao. Có hai đường:
   - Chế độ api: `jira-connections-manager.tsx` → `syncIntegrationAction` → `POST /api/v1/integrations/{id}/sync?assignee=...` → `jira_client.build_jql` sinh `(<JQL kết nối>) AND assignee in (...)`.
   - Chế độ file: `jira-sync-manager.tsx` → `syncJiraAction` (`app/jira-actions.ts`) dựng JQL bằng TypeScript theo cùng quy tắc.

   User muốn kéo cả những issue mình **tạo/báo cáo** nhưng giao cho người khác: `assignee in (...) OR reporter in (...)`.
2. **Hiển thị.** Task không lưu reporter. `BASE_FIELDS` (`jira_client.py`) và `JIRA_BASE_FIELDS` (`jira-actions.ts`) đều không xin field `reporter`. `build_raw_payload` cũng không giữ nó, nên **không backfill được** từ dữ liệu cũ (xem 2.3).

### 1.2. In-scope

- Backend: tham số mới `reporter` (lặp) cho `POST /integrations/{id}/sync`, ghép OR với `assignee`. Xin field `reporter` từ Jira, ánh xạ `displayName` vào cột mới `tasks.reporter`. Thêm vào allowlist `raw_payload`. `TaskRead.reporter`. `TaskUpsert.reporter` (dùng chung cho upsert-batch, Excel chế độ api và Jira sync). Nhập JSON B1 (`ImportTask.reporter`). pytest.
- Web: ô "Theo người" ở **cả hai** component có thêm lựa chọn vai trò (mặc định "Cả hai", R1). Server Action validate vai trò. `lib/api.ts::syncIntegration` gửi `reporter`. `task-item.tsx` hiện reporter. Chế độ file: `SCHEMA_VERSION` 7 → 8 có bước migrate, `syncJiraAction` xin và ghi `reporter`, Excel đọc cột `Reporter`, CSV xuất/nhập cột `reporter`.
- `lib/generated/openapi.d.ts` sinh lại (không sửa tay).

### 1.3. Out-of-scope

- Reporter **không** ảnh hưởng quyền hay "việc của tôi": `access.task_view_clause` (`view=mine`) và `access.task_permissions` vẫn chỉ xét `assignee`. Muốn task mình báo cáo hiện ở "Hôm nay" là epic riêng (R7).
- Lọc `GET /tasks?reporter=`, nhóm theo reporter ở `/team`, index trên `tasks.reporter`.
- Đổi JQL dự phòng khi kết nối không có JQL (`current_users` / alias của người gọi sau epic auth) sang có reporter (R6).
- Sửa reporter bằng tay: không có trong `TaskCreate`/`TaskUpdate`. Reporter là dữ liệu do nguồn sở hữu.
- Lưu email hay `accountId` của reporter: **cấm** (PII). Chỉ `displayName`.

## 2. Thay đổi dữ liệu

### 2.1. Bảng

| Bảng | Thay đổi | Index/Constraint | Ghi chú migration (downgrade?) |
|---|---|---|---|
| `tasks` | Thêm `reporter VARCHAR(200) NULL`, không default | Không index, không CHECK (R4) | Upgrade: `SET LOCAL lock_timeout = '5s'` rồi `add_column`. Cột nullable không default nên chỉ đổi metadata, không viết lại bảng. Downgrade: `drop_column`. Mất tên reporter, lần sync đầy đủ sau khi upgrade lại sẽ điền lại (nguồn là Jira). Không cần dump trước khi hạ. |

### 2.2. Mã nguồn cho backend-dev

**Model** (`app/models/task.py`, khối "Nội dung", ngay dưới `assignee`), kèm comment một dòng giải thích WHY: tên hiển thị của người tạo issue ở nguồn, chỉ để xem, không quyết định quyền hay view, không lưu email.

```python
reporter: Mapped[str | None] = mapped_column(String(200), default=None)
```

**Migration** `apps/core/migrations/versions/<rev>_add_tasks_reporter.py`, viết theo mẫu `c3d8e5f1a7b4_add_tasks_assignee.py`:

```python
def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.add_column("tasks", sa.Column("reporter", sa.String(length=200), nullable=True))

def downgrade() -> None:
    # Mất tên reporter. Dữ liệu do Jira sở hữu: sync đầy đủ sau khi upgrade lại sẽ điền lại.
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.drop_column("tasks", "reporter")
```

`conftest.py` không cần sửa.

### 2.3. Không backfill được

`raw_payload` của task cũ không có `reporter`, vì allowlist hiện tại không giữ nó. Cột sẽ là `NULL` cho mọi task cho tới khi task được sync lại. Lượt sync có `since` chỉ chạm issue cập nhật gần đây. Muốn điền hết thì sau khi deploy phải chạy **một lượt "Tất cả"** (không `since`, không lọc người). Orchestrator ghi việc này vào hướng dẫn deploy.

### 2.4. Chính sách ghi khi cập nhật (R3)

Đề xuất: reporter **luôn được cập nhật** theo Jira, **không** đưa vào `CREATE_ONLY` (`integration_sync_service.py`).

- Lý do: `CREATE_ONLY` (`priority`, `assignee`, `project_key`) tồn tại để giữ giá trị User sửa tay. Reporter không sửa tay được (không có trong `TaskUpdate`), nên không có gì để giữ. Nếu để create-only thì 738+ task đang có sẽ **không bao giờ** có reporter.
- Cách làm: thêm `"reporter"` vào `_SYNCED_FIELDS` của `task_sync_service.py`. `_wanted_values` chỉ ghi khi item có gửi khoá (`model_fields_set`), nên client upsert-batch không gửi `reporter` sẽ không xoá giá trị đang có.
- Hệ quả cần biết: lượt sync đầy đủ đầu tiên sau deploy sẽ tính mọi task là `updated` (`reporter: null → tên`), sinh một event `updated` và đổi `updated_at` cho từng task. Đây là việc một lần. Sau đó, nhập lại một file JSON cũ sẽ báo `file_older_than_db` cho các task này. Hành vi này đúng, nhưng ghi vào hướng dẫn.
- Jira trả `reporter: null` (issue tạo ẩn danh hoặc reporter bị xoá) thì ghi `NULL`, giống `assignee`.

## 3. API contract

Prefix `/api/v1`. Xác thực theo trạng thái hiện hành của route (hôm nay là `X-API-Key` + `X-Import-Secret`; sau epic auth là JWT, xem `docs/specs/auth-multiuser.md` dòng `/integrations/{id}/sync`). Epic này **không** đổi lớp xác thực.

### 3.1. Bảng endpoint

| Method | Path | Request | Response | Lỗi |
|---|---|---|---|---|
| POST | `/integrations/{id}/sync` | Query hiện có (`since`, `assignee` lặp) + **`reporter`** lặp: `list[str(1..100, pattern _NAME_PATTERN)]`, tối đa 20 | `SyncResult` (không đổi shape) | 422: quá 20 tên ở một tham số, tên rỗng/dài/có ký tự điều khiển, JQL sau ghép vượt 4000 ký tự ("JQL quá dài"). Các lỗi khác như cũ. |
| GET | `/tasks`, `/tasks/{id}`, `/tasks/agenda`... | Không đổi | `TaskRead` có thêm **`reporter: str \| None`** (bắt buộc, không default, R5) | Không đổi |
| POST | `/tasks/upsert-batch` | `TaskUpsert` có thêm **`reporter: str \| None`** (tuỳ chọn, max 200) | `TaskUpsertResult` không đổi | 422 nếu dài hơn 200 |
| POST | `/import/datafile` | `ImportTask.reporter: str \| None` (tuỳ chọn, max 200) | Không đổi | Không đổi |

`POST/PATCH /tasks` **không** nhận `reporter`. `TaskCreate`/`TaskUpdate` không có field này. Pydantic mặc định bỏ qua khoá lạ, nên client gửi `reporter` cũng không ghi được gì.

### 3.2. Ngữ nghĩa JQL (`jira_client.build_jql`)

Chữ ký mới (giữ tương thích vị trí):

```python
def build_jql(
    config_jql: str | None,
    current_users: list[str],
    since_minutes: int | None,
    assignees: list[str] | None = None,
    reporters: list[str] | None = None,
) -> str
```

1. **Base** giữ nguyên quy tắc hiện tại: có `config_jql` thì dùng nguyên, hoặc đổi danh sách mã dự án thành `project in (...)`. Không có `config_jql` mà có người (assignee **hoặc** reporter) thì base rỗng và bỏ qua `current_users`. Không có gì thì 422 như cũ.
2. **Điều kiện người:** `conds = []`. Có assignee thì thêm `assignee in (<jql_string...>)`. Có reporter thì thêm `reporter in (<jql_string...>)`. Hai điều kiện nối bằng `OR` và **bọc ngoặc** khi có cả hai. Lý do: trong JQL, `AND` ưu tiên hơn `OR`. Thiếu ngoặc thì `project in ("DBA") AND assignee in ("X") OR reporter in ("X")` kéo reporter X trên **mọi** project, tức kéo ra ngoài phạm vi kết nối.
3. **Quan hệ với JQL của kết nối: `AND`** (R2). JQL kết nối là phạm vi do chủ kết nối đặt. Lọc người chỉ được thu hẹp, không được mở rộng.
4. `since` bọc ngoài cùng như cũ. `ORDER BY updated DESC` luôn ở cuối, `ORDER BY` của JQL kết nối bị bỏ bằng `_ORDER_BY_RE` như cũ.
5. Mọi tên đi qua `jql_string`. Không chuỗi nào từ client được nối thẳng vào JQL.
6. Chỉ có `assignees` (không `reporters`): output **giống hệt từng ký tự** hôm nay. Test cũ phải pass, không được sửa.

Chuỗi kỳ vọng (dùng làm test):

| Đầu vào | JQL |
|---|---|
| config `DBA`, A=`["X"]`, R=`["X"]` | `(project in ("DBA")) AND (assignee in ("X") OR reporter in ("X")) ORDER BY updated DESC` |
| không config, A=`["X"]`, R=`["X"]` | `(assignee in ("X") OR reporter in ("X")) ORDER BY updated DESC` |
| không config, R=`["X"]`, `current_users=["me"]` | `reporter in ("X") ORDER BY updated DESC` |
| config `project = DBA ORDER BY created`, R=`["Y"]` | `(project = DBA) AND reporter in ("Y") ORDER BY updated DESC` |
| không config, A=R=`["X"]`, since 10 | `((assignee in ("X") OR reporter in ("X"))) AND updated >= -10m ORDER BY updated DESC` |

### 3.3. Service và route

- `api/v1/integrations.py::sync_connection`: thêm tham số `reporter` cùng kiểu Annotated với `assignee` (tách `PersonName` thành alias dùng chung để hai tham số không lệch), mô tả "Kéo cả issue do những người này báo cáo (OR với assignee)". Truyền `reporters=reporter`. Cập nhật `description` của route.
- `integration_sync_service.run_sync(..., assignees=None, reporters=None)` → `_run` → `build_jql(..., assignees, reporters)`.
- Audit `start`: thêm `reporter_count=len(reporters or [])`. **Không** log tên (PII).
- Nhánh "Lượt kéo theo người: last_sync_at KHÔNG được cập nhật" áp khi `assignees or reporters`.

### 3.4. Ánh xạ (`jira_mapping.py`)

- `jira_client.BASE_FIELDS` thêm `"reporter"`.
- `map_issue`: `reporter = clean_text(_obj(fields.get("reporter")).get("displayName")) or None`. Dài hơn `MAX_REPORTER_LEN` thì cắt, `strip()`, và thêm note `"tên reporter quá dài nên bị cắt"`. Thêm `"reporter": reporter` vào `data`. **Chỉ** đọc khoá `displayName`, không đọc `emailAddress`, `accountId` hay `avatarUrls`.
- `schemas/task.py`: `MAX_REPORTER_LEN = MAX_ASSIGNEE_LEN` (200), cùng hằng số với cột.
- `build_raw_payload`: thêm `("reporter", "displayName")` vào vòng `pick_name`. Giá trị cắt về `MAX_REPORTER_LEN`.
- Cập nhật khối "Điểm lệch có chủ đích" cuối file: reporter luôn cập nhật, không create-only, kèm lý do (2.4).
- `TaskUpsert`: `reporter: str | None = Field(default=None, max_length=MAX_REPORTER_LEN)`. Thêm vào `_drop_nul`. Validator `clean_assignee` dùng chung (đổi tên thành `clean_person_name` là tuỳ chọn, giữ alias cũ).
- `task_sync_service`: `"reporter"` vào `_SYNCED_FIELDS`. `_build_task` đặt `reporter=item.reporter`.
- `TaskRead`: `reporter: str | None`, không default, đặt cạnh `assignee`.
- Nhập B1: `schemas/imports.py::ImportTask.reporter: str | None = Field(default=None, max_length=200)` + `clean_assignee`. `import_service.TASK_FIELDS` thêm `"reporter"`. `_parse_task` đặt `values["reporter"] = m.reporter`. File không có khoá `reporter` (v1-v7) thì `fallback.add("reporter")`: tạo mới thì NULL, ghi đè thì giữ giá trị DB. `SUPPORTED_DATAFILE_VERSION = 8` (khớp web, mục 4.2).

## 4. Thay đổi Web

### 4.1. Ô "Theo người" (R1)

Cả `components/jira-connections-manager.tsx` (api) và `components/jira-sync-manager.tsx` (file) giữ **một** ô nhập tên như hôm nay, thêm một `<select>` "Vai trò" ngay cạnh:

| value | Nhãn | Gửi đi |
|---|---|---|
| `both` (mặc định) | Được giao hoặc báo cáo | Cùng danh sách cho cả assignee lẫn reporter |
| `assignee` | Chỉ người được giao | Như hôm nay |
| `reporter` | Chỉ người báo cáo | Chỉ reporter |

Sửa câu hướng dẫn dưới ô: "Tên hiển thị trên Jira, cách nhau bằng dấu phẩy. Lọc theo người KẾT HỢP (AND) với JQL của kết nối." Placeholder không đổi. Ô tên trống thì `select` không có tác dụng.

### 4.2. Chế độ file (`lib/store`)

Đề xuất làm đủ (R9), vì `jira-sync-manager.tsx` là đường User đang dùng:

- `lib/store/types.ts`: `SCHEMA_VERSION = 8`, thêm dòng lịch sử "8 → thêm reporter cho task".
- `lib/store/json-file.ts::migrate`: bước `v7 → v8` đặt `reporter = null` cho task chưa có khoá (`typeof task.reporter !== "string"` và khác `null`). Chạy lại không đổi dữ liệu.
- `lib/store/engine.ts::makeTask`: `reporter: partial.reporter ?? null`.
- `lib/store/csv.ts`: thêm cột `reporter` vào `TASK_COLUMNS` (xuất). Khi nhập, cột vắng hoặc ô rỗng thì `null`.
- `.agents/rules/web-conventions.md` ("Hiện tại đang ở v7") thuộc orchestrator.

### 4.3. Server Action

| Action | Thay đổi | Validate (Server Action là endpoint công khai) |
|---|---|---|
| `syncIntegrationAction(id, secret, since, assignees, role)` (`app/jira-actions.ts`) | Tham số mới `role`. `both` gửi `picked` cho cả `assignees` lẫn `reporters`; `assignee` gửi `assignees`; `reporter` gửi `reporters`. | `role` chỉ nhận đúng `"both" \| "assignee" \| "reporter"`. Vắng/`undefined` thì coi là `"assignee"` (giữ hành vi cho client cũ). Giá trị khác thì trả lỗi, không đoán. Tên vẫn qua `parseAssignees` (≤ 20 tên, ≤ 100 ký tự, không ký tự điều khiển). |
| `syncJiraAction(formData)` (chế độ file) | Đọc `formData.get("people_role")` theo cùng quy tắc. Dựng điều kiện người **giống hệt** 3.2 (ngoặc, OR, AND với base), tên qua `jqlQuote`. `JIRA_BASE_FIELDS` thêm `"reporter"`. Task mới và task đã có đều nhận `reporter = clean(fields.reporter?.displayName)` cắt 200 ký tự, hoặc `null`. **Không** đọc `emailAddress`. | Như trên |
| `importBulkTasksAction` (`app/actions-import.ts`, Excel/URL) | Đọc cột `Reporter` nếu sheet **có** header đó (tên cột Jira export). Ô trống thì `null`. Sheet không có cột thì **không** gửi khoá `reporter` (api: không có trong item upsert; file: không đụng giá trị đang có). | Cắt 200 ký tự |

Không thêm Server Action mới.

### 4.4. `lib/api.ts`

`syncIntegration(id, secret, since?, people: { assignees?: string[]; reporters?: string[] } = {})`. Mỗi tên `params.append("assignee"|"reporter", name)`. Đây là đổi chữ ký nên phải sửa nơi gọi duy nhất (`syncIntegrationAction`).

### 4.5. `components/task-item.tsx`

Khi `task.reporter` có giá trị, hiện badge ngay sau badge `@assignee`: text node `Báo cáo: {task.reporter}`, màu trung tính (slate) để không nhầm với assignee (cam), `title="Người báo cáo trên Jira"`. Không `dangerouslySetInnerHTML`. R5b: có ẩn badge khi reporter trùng assignee hay không.

### 4.6. `lib/types.ts`

Không sửa tay field. `Task` tự có `reporter: string | null` sau khi sinh lại `openapi.d.ts`. Vì field là required (R5), `tsc` sẽ báo lỗi ở mọi object literal tạo `StoredTask` (`engine.ts::makeTask`, `jira-actions.ts` nhánh tạo task, `actions-import.ts` nhánh tạo mới, có thể cả `csv.ts`/`transfer.ts`). Đây là lưới an toàn có chủ đích. Sửa từng chỗ bằng `reporter: ... ?? null`, **không** nới thành optional.

## 5. Ownership (không agent nào sửa file của agent khác)

**backend-dev** (`apps/core/**` + smoke test):
- `app/models/task.py`
- `migrations/versions/<rev>_add_tasks_reporter.py` (mới; `down_revision` = kết quả `alembic heads` lúc code)
- `app/schemas/task.py` (`MAX_REPORTER_LEN`, `TaskRead.reporter`)
- `app/schemas/task_upsert.py`, `app/schemas/imports.py`
- `app/services/jira_client.py`, `app/services/jira_mapping.py`, `app/services/integration_sync_service.py`, `app/services/task_sync_service.py`, `app/services/import_service.py`
- `app/api/v1/integrations.py`
- `tests/test_jira_client.py`, `tests/test_jira_sync_api.py`, `tests/test_task_upsert.py`, `tests/test_task_api.py`, `tests/test_import_unit.py`, `tests/test_import_service.py`
- `scripts/smoke-test.sh` (assert `GET /tasks` trả khoá `reporter`)

**frontend-dev** (`apps/web/**` trừ `lib/generated/**`):
- `app/jira-actions.ts`, `app/actions-import.ts`
- `lib/api.ts`
- `lib/store/types.ts`, `lib/store/json-file.ts`, `lib/store/engine.ts`, `lib/store/csv.ts` (và file nào khác trong `lib/store/` mà `tsc` báo lỗi vì `reporter` required; báo lại tên file trong kết quả)
- `components/jira-connections-manager.tsx`, `components/jira-sync-manager.tsx`, `components/task-item.tsx`

**orchestrator:**
- Sinh lại `apps/web/lib/generated/openapi.d.ts` sau khi backend xong: `make gen-types` (cần stack chạy). Không có Docker thì dùng cách không Docker ở `docs/specs/task-scope.md` mục 5.
- Docs: `docs/API_REFERENCE.md` (`reporter` ở sync và `TaskRead`), tài liệu Jira sync/deploy (cần một lượt sync "Tất cả" sau deploy, mục 2.3), `.agents/rules/web-conventions.md` (v7 → v8), `docs/AI_HANDOFF_STATE.md`, đăng ký spec này trong `apps/web/lib/docs.ts`.

**Không ai sửa:** `data/**`, `app/services/access.py`, `app/core/permissions.py`, các model khác.

**Thứ tự:** backend-dev → orchestrator sinh types → frontend-dev. Có thể làm song song trong hai worktree, nhưng `tsc` của web chỉ có nghĩa sau khi sinh types.

## 6. Tiêu chí nghiệm thu (kiểm chứng được)

### 6.1. Backend (chạy trong `apps/core/`)

- [ ] `uv run ruff check app migrations tests` và `uv run ruff format --check app migrations tests` → exit 0 (hoặc `make lint`).
- [ ] `uv run alembic heads` → đúng một head, là revision mới.
- [ ] Trên DB `_test`: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head && alembic check` → bốn lệnh exit 0, "No new upgrade operations detected".
- [ ] `TEST_DATABASE_URL=… uv run pytest -q` → pass, không test `db` nào bị skip (thiếu Postgres thì **không** tính là pass).
- [ ] `make smoke` pass (khi có Docker), có assertion mới cho khoá `reporter`.

### 6.2. Test bắt buộc

**`tests/test_jira_client.py` (thuần, không DB):**
1. `build_jql`: đúng từng chuỗi của bảng 3.2.
2. Hồi quy: mọi test `assignees` hiện có pass **mà không sửa**.
3. Injection: reporter `x") OR project = SECRET OR reporter in ("y` → nằm trọn trong một chuỗi đã escape. JQL bắt đầu bằng `reporter in (` (khi chỉ có reporter) và không có `OR project` ngoài ngoặc kép.
4. `reporters` có mà `config_jql` rỗng thì bỏ qua `current_users`. Không config, không user, không người → `ValidationError`.
5. Ngoặc: config `DBA` + A + R → chuỗi chứa `AND (assignee in (` và kết thúc nhóm bằng `reporter in ("X"))`.
6. 20 assignee + 20 reporter dài 100 ký tự → `ValidationError("JQL quá dài")` (vượt 4000).
7. `"reporter" in BASE_FIELDS`. Body của request search (qua transport giả) có `reporter` trong `fields`.
8. `map_issue`: reporter `{"displayName": "Hùng Đoàn", "emailAddress": "a@b.c", "accountId": "abc"}` → `item.reporter == "Hùng Đoàn"`. `json.dumps(item.model_dump(mode="json"))` không chứa `a@b.c` lẫn `abc`.
9. Reporter vắng, `null`, hoặc `{}` → `None`. `displayName` có `\x00`/`\x1b`/U+202E/`\r` → được làm sạch như assignee.
10. Reporter dài 500 → cắt còn 200, có note chứa `"reporter"`.
11. Sửa `test_raw_payload_is_an_allowlist`: allowlist thêm `"reporter"`. `payload["fields"]["reporter"] == {"displayName": ...}`. `emailAddress` vẫn **không** có trong payload.

**`tests/test_jira_sync_api.py` (DB + transport giả):**
12. `POST /sync?assignee=A&reporter=A` → JQL gửi tới Jira giả đúng bảng 3.2. `reporter` 21 lần → 422. `reporter=` rỗng → 422. Có `\x01` → 422. Dài 101 → 422.
13. Sau sync, task mới có `reporter` đúng. `GET /tasks/{id}` trả `reporter`.
14. Task đã có (tạo khi chưa có cột, `reporter IS NULL`) → sync lần nữa → `reporter` được điền, `updated == 1`, event `updated` có `changes.reporter = {from: null, to: ...}`.
15. Jira đổi reporter → task cập nhật theo (không create-only). Cùng lượt đó `assignee`/`priority` User đã sửa vẫn giữ (CREATE_ONLY không đổi).
16. Sync lại không đổi gì → `unchanged`, không event mới (idempotent).
17. Lượt có `reporter` (không `assignee`) → `last_sync_at` không đổi, có cảnh báo "Lượt kéo theo người".
18. Task `scope=personal` trùng khoá → `skipped_personal`, `reporter` không đổi.

**`tests/test_task_upsert.py` (parity upsert-batch):**
19. Item có `reporter` → tạo/cập nhật đúng. Item **không** gửi khoá `reporter` → giá trị DB giữ nguyên. Gửi `null` tường minh → xoá về NULL. Dài 201 → lỗi validate.

**`tests/test_task_api.py`:**
20. `TaskRead` luôn có khoá `reporter` (kể cả `null`). `POST /tasks` và `PATCH /tasks/{id}` kèm `reporter` → bị bỏ qua, DB vẫn NULL.

**`tests/test_import_unit.py` / `test_import_service.py`:**
21. File không có `reporter`: tạo mới → NULL. Ghi đè task DB đang có reporter → giữ nguyên (fallback). File có `reporter` → ghi đúng. `schema_version: 8` → nhận, `9` → 422.

### 6.3. Types (orchestrator)

- [ ] `grep -n "reporter" apps/web/lib/generated/openapi.d.ts` có trong `TaskRead` (không có `?`), `TaskUpsert`, và tham số query của `/api/v1/integrations/{connection_id}/sync`.
- [ ] `git diff --stat apps/web/lib/generated/openapi.d.ts` chỉ chứa phần liên quan.

### 6.4. Web (frontend-dev)

- [ ] `cd apps/web && npx tsc --noEmit` → exit 0.
- [ ] `grep -n '"reporter"' apps/web/app/jira-actions.ts` → có trong `JIRA_BASE_FIELDS`.
- [ ] `grep -rn "emailAddress" apps/web/app apps/web/lib apps/web/components` → không có chỗ nào **đọc** email reporter/assignee.
- [ ] `grep -n "SCHEMA_VERSION = 8" apps/web/lib/store/types.ts` → 1 dòng. `grep -n "schema_version < 8" apps/web/lib/store/json-file.ts` → có.
- [ ] `grep -n "dangerouslySetInnerHTML" apps/web/components/task-item.tsx` → rỗng.
- [ ] Nếu repo có test thuần cho JQL phía web: thêm case cho bảng 3.2. Nếu không, orchestrator chạy một script `$SCRATCH/jql-parity.ts` (ngoài repo) so chuỗi JQL của `syncJiraAction` (tách hàm dựng JQL thành hàm thuần export được) với bảng 3.2.

### 6.5. Kịch bản tay (UAT)

Chế độ file, **trên bản sao** `data/` (`DATA_DIR` trỏ tới bản copy; không chạy thêm `next dev` song song với server của User):
1. Mở web → file trong `DATA_DIR` được ghi lại `schema_version: 8`, mọi task có `"reporter": null`.
2. `/data` → Đồng bộ Jira, kết nối JQL `DBA`, ô người "Tên tôi", vai trò "Được giao hoặc báo cáo", 30 ngày → có cả issue tôi tạo nhưng giao người khác. Task hiện badge "Báo cáo: …".
3. Vai trò "Chỉ người được giao" → kết quả như trước epic.

Chế độ api:
4. `/data` → kết nối → "Cào ngay" với tên + vai trò "Cả hai" → kết quả có task mình báo cáo. `make psql`: `SELECT count(*) FROM tasks WHERE reporter IS NOT NULL` > 0.
5. Lượt "Tất cả" không lọc người → `last_sync_at` được cập nhật, reporter điền cho task cũ.

### 6.6. Review

`db-reviewer` (migration, lock_timeout, model khớp migration), `code-reviewer`, `security-auditor` (JQL injection ở cả Python lẫn TS, PII của reporter, Server Action nhận `role`).

## 7. Rủi ro & quyết định cần User chốt

### 7.1. Quyết định (đề xuất của architect)

| # | Câu hỏi | Đề xuất |
|---|---|---|
| R1 | API và UI cho lọc reporter | API: thêm query `reporter` (lặp) riêng, **giữ** `assignee` đúng nghĩa cũ. Hai tham số nối `OR`. Không đổi tên `assignee`, vì client cũ không phải sửa. UI: một ô tên + select vai trò, mặc định **"Cả hai"**. Phương án gọn hơn là bỏ select, luôn "Cả hai": khi đó không còn cách kéo riêng theo người được giao. |
| R2 | Quan hệ với JQL của kết nối | `AND`: `(<JQL kết nối>) AND (assignee in … OR reporter in …)`. Lọc người chỉ thu hẹp phạm vi kết nối, không mở rộng ra project khác. |
| R3 | `reporter` create-only hay luôn cập nhật | **Luôn cập nhật** (vào `_SYNCED_FIELDS`, không vào `CREATE_ONLY`). Hệ quả một lần: lượt sync đầy đủ đầu tiên đánh `updated` + event cho mọi task cũ. |
| R4 | Index cho `tasks.reporter` | Không. Chưa có truy vấn lọc theo reporter. |
| R5 | `TaskRead.reporter` required-nullable hay optional | Required-nullable (`str \| None`, không default), giống `assignee`. Ép `tsc` bắt mọi chỗ tạo task ở chế độ file. R5b: badge hiện cả khi reporter trùng assignee? Đề xuất **ẩn khi trùng** để bớt nhiễu. |
| R6 | JQL dự phòng (kết nối không có JQL, dùng `current_users`/alias) có thêm `OR reporter in (...)` không | Không, giữ `assignee in (...)`. Muốn đổi thì làm sau epic auth (fallback đổi sang alias). |
| R7 | Reporter có tính vào "việc của tôi" (`view=mine`) hay quyền sửa không | Không, ngoài phạm vi. Đụng `access.py` của epic auth, cần spec riêng. |
| R8 | Thứ tự với epic auth (`feat/auth-multiuser`, chưa commit) | Code **sau** khi epic auth được commit, trên cùng nhánh hoặc nhánh tách từ nó. Migration nối sau `b2f7a9c1d4e6` (hoặc head mới hơn nếu auth thêm migration). Nếu auth bỏ `X-Import-Secret` ở `/sync` trước, epic này không bị ảnh hưởng vì chỉ thêm query param. |
| R9 | Chế độ file có làm không | **Có, đầy đủ**: `SCHEMA_VERSION` 8 + migrate, `syncJiraAction`, Excel, CSV. `jira-sync-manager.tsx` (chế độ file) là đường User đang dùng, và `TaskRead.reporter` required buộc phải chạm `lib/store`. Backend `SUPPORTED_DATAFILE_VERSION = 8` cùng lúc. |

### 7.2. Rủi ro

- **Ngoặc JQL sai ở một trong hai bản (Python/TS)** sẽ kéo issue ngoài project và có thể chạm trần dung lượng. Giảm thiểu: cùng bảng 3.2 cho cả hai bên, test 5 + kiểm chứng 6.4.
- **Lượt "Cả hai" kéo nhiều hơn hẳn** với người tạo nhiều ticket, nên dễ chạm trần 100 trang/50 MB. Thông báo truncated hiện có đã đủ (bảo thu hẹp JQL/since).
- **PII:** tên hiển thị là PII nhẹ, giống `assignee` đang lưu. Không lưu email/accountId. Không log tên trong audit (chỉ đếm). Jira có thể ẩn `displayName` theo cài đặt riêng tư, khi đó lưu đúng giá trị Jira trả hoặc NULL.
- **Một lượt `updated` hàng loạt sau deploy** (R3): sổ sự kiện của mọi task Jira có thêm một dòng. `updated_at` đổi, nên nhập lại file JSON cũ sẽ báo "file cũ hơn DB".
- **Reporter NULL cho tới lượt sync đầy đủ** (2.3). User có thể nghĩ tính năng hỏng nếu chỉ chạy "Cập nhật nhanh".
- **Va chạm với epic auth đang dở** trên cùng file (`schemas/task.py`, `models/task.py`, `task_sync_service.py`, `lib/types.ts`): làm tuần tự theo R8 để tránh xung đột merge và hai head Alembic.

## Phụ lục A. Đối chiếu code thật

1. Có **hai** component sync. `jira-sync-manager.tsx` là chế độ file (TS gọi Jira trực tiếp qua `syncJiraAction`). Chế độ api dùng `jira-connections-manager.tsx` → `syncIntegrationAction`. Đề bài chỉ nêu cái thứ nhất, spec sửa cả hai.
2. `syncJiraAction` (file) khi cập nhật task đã có **không** ghi `assignee`/`priority`/project (create-only, khớp backend). `reporter` sẽ được ghi ở cả nhánh tạo lẫn nhánh cập nhật (R3).
3. `tests/test_jira_client.py::test_raw_payload_is_an_allowlist` đã đưa `reporter={"emailAddress": ...}` vào làm dữ liệu cấm. Test phải sửa allowlist nhưng vẫn giữ assert `emailAddress` không có trong payload.
4. `MAX_ASSIGNEE_LEN = 200` ở `schemas/task.py`, nhưng tham số query `assignee` của `/sync` giới hạn 100 ký tự (`integrations.py`, khớp `parseAssignees` của web). `reporter` dùng cùng giới hạn 100 cho query, 200 cho dữ liệu lưu.
5. Web `SCHEMA_VERSION` hiện là 7, backend `SUPPORTED_DATAFILE_VERSION = 7`.
