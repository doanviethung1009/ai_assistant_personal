# Spec: Người dùng tự chọn múi giờ hiển thị, và sửa lỗi quá hạn của hạn Jira

- Trạng thái: DRAFT
- Tác giả: architect
- Ngày: 2026-10-09
- Nhánh lúc viết: `main` (sạch phần code liên quan; thay đổi chưa commit chỉ thuộc epic Proxmox)
- Alembic head lúc viết spec: `f3a8c1d5e7b9` (drop ai_logs). Migration của epic này có `down_revision = "f3a8c1d5e7b9"`.
- Đã đối chiếu với code thật. Các điểm lệch giữa tài liệu và code nằm ở **Phụ lục A**.

## 1. Bối cảnh & phạm vi

### 1.1. Vấn đề

**(a) Múi giờ cố định ở hai nơi, cả hai không đổi được lúc chạy.**

| Tầng | Nguồn | Nơi dùng |
|---|---|---|
| Backend | `settings.display_timezone` (`core/config.py:75`, env, mặc định `Asia/Ho_Chi_Minh`) | `services/clock.py::display_tz()`; `task_service.get_stats` đọc thẳng `settings.display_timezone` trong `func.timezone(...)` (dòng ~580); `task_sync_service._to_utc` (~210, qua `clock`); `api/v1/system.py` trả ra `SystemInfo.display_timezone` |
| Web | `NEXT_PUBLIC_DISPLAY_TZ` (`lib/format.ts:4`, **nhúng lúc build**) | 4 formatter module-level trong `format.ts`, `todayInDisplayTz()`, `lib/store/engine.ts:60, 606` (chế độ file) |

Hai giá trị này độc lập. Đặt lệch nhau thì web hiển thị một ngày còn backend tính "hôm nay" theo ngày khác. Riêng biến web nhúng lúc build nên image dùng chung cho uat/prod (xem `docs/specs/proxmox-deploy.md`) không thể có múi giờ khác nhau.

**(b) Task Jira có hạn hôm nay bị báo quá hạn từ 07:00 sáng (giờ VN).**

- `jira_mapping._parse_due` (dòng 138) đổi `duedate` của Jira (ngày thuần `YYYY-MM-DD`) thành `00:00 UTC` của ngày đó. Chế độ file làm y hệt (`app/jira-actions.ts:351`, `new Date("YYYY-MM-DD").toISOString()`).
- Mọi chỗ xét quá hạn so `due_at < now`: `TaskRead.is_overdue` (`schemas/task.py:193`), `get_agenda.overdue` (`task_service.py:484`), `get_stats.overdue_total` (~607), cùng các bản sao ở `engine.ts` (511, 559, 652).
- Kết quả: hạn ngày 09/10 lưu thành `2026-10-09T00:00Z` = 07:00 ngày 09/10 giờ VN. Từ 07:00 task đã "quá hạn" dù người dùng hiểu hạn là cuối ngày 09/10.

**(c) Đổi hạn trên Jira không cập nhật về.** `due_at` nằm trong `CREATE_ONLY` (`integration_sync_service.py:57`), nên sync chỉ ghi hạn lúc tạo task. Chế độ file cố ý cùng ngữ nghĩa.

### 1.2. Mô hình sau epic

1. **Một nguồn sự thật cho múi giờ:** dòng `app_settings.key = 'display_timezone'`. Không có dòng thì dùng env `DISPLAY_TIMEZONE` (backend) làm mặc định. Web không tự quyết múi giờ nữa, mà lấy từ backend (chế độ api) hoặc từ `meta` của file JSON (chế độ file).
2. **Hạn "cả ngày" là khái niệm tường minh:** cột mới `tasks.due_all_day`. Với task cả ngày, `due_at` luôn là `00:00:00 UTC` của **ngày lịch** (cách lưu chuẩn, không phụ thuộc múi giờ), và quy tắc quá hạn là **ngày hạn < hôm nay theo múi giờ người dùng**. Task có giờ cụ thể giữ quy tắc cũ `due_at < now`.
3. **Sync cập nhật hạn có điều kiện:** Jira đổi hạn thì task cập nhật theo, **trừ khi** người dùng đã sửa hạn tay ở hệ thống này (phát hiện bằng `raw_payload.fields.duedate` lần sync trước). Xem quyết định Q4.

Vì sao chọn cột `due_all_day` mà không đổi cách lưu thành "23:59:59 giờ local" (phương án A ở mục 7.2): cách lưu chuẩn theo UTC giữ nguyên đúng khi người dùng **đổi múi giờ** về sau, không phải viết lại dữ liệu.

### 1.3. In-scope

- **Backend:** `SettingKey.DISPLAY_TIMEZONE`; migration DROP/ADD `ck_app_settings_key_valid` và thêm `tasks.due_all_day` (kèm backfill, CHECK); `clock.py` đọc múi giờ lúc chạy, có cache ngắn; thay mọi chỗ đọc thẳng `settings.display_timezone`; validate env lúc khởi động; API GET/PUT setting và danh sách IANA; quy tắc quá hạn mới ở `is_overdue`, agenda, stats; `_parse_due` đặt `due_all_day=True`; cập nhật `due_at` có điều kiện trong Jira sync; nhập JSON nhận `display_timezone` và `due_all_day`; pytest; `scripts/smoke-test.sh`.
- **Web (cả ba chế độ `DATA_SOURCE`):** bỏ hằng `DISPLAY_TZ`, mọi hàm format nhận `tz` tường minh; `TimezoneProvider` ở root layout để server render và client hydrate cùng một múi giờ; component chọn múi giờ ở trang `/data` (cạnh "Tên của tôi"); hiển thị giá trị hiệu lực ở `/system`; Server Action lưu múi giờ; hiển thị hạn cả ngày dạng ngày (không giờ); `QuickAddForm` quy đổi `datetime-local` theo múi giờ đã chọn thay vì múi giờ browser; chế độ file: `SCHEMA_VERSION` 6 → 7 (backfill `due_all_day`), `meta.display_timezone`, quy tắc quá hạn và cập nhật hạn có điều kiện ở `jira-actions.ts`.

### 1.4. Out-of-scope

- Múi giờ theo từng người dùng (multi-user). Hệ thống một người dùng, setting là toàn cục.
- Chọn locale (`vi-VN` giữ nguyên) và định dạng 12h/24h.
- Cho người dùng tạo task tay với hạn "cả ngày" (`TaskCreate`/`TaskUpdate` **không** nhận `due_all_day` ở epic này; sửa `due_at` qua PATCH luôn đặt `due_all_day=false`). Có thể làm ở epic sau.
- Nhập Excel/URL (`lib/excel-upsert.ts`, `app/actions-import.ts`): vẫn gửi `due_at` như hiện tại, không gửi `due_all_day`. Ghi nhận ở rủi ro R6.
- Bộ lọc `due_before` của `GET /tasks` (`task_service.py:165`): giữ so sánh thô theo `due_at`.
- Gỡ biến `NEXT_PUBLIC_DISPLAY_TZ` khỏi Dockerfile/compose. Epic này hạ nó thành giá trị dự phòng; gỡ hẳn để epic sau (Q6).

## 2. Thay đổi dữ liệu

### 2.1. Bảng

| Bảng | Thay đổi | Index/Constraint | Ghi chú migration (downgrade?) |
|---|---|---|---|
| `app_settings` | Khoá mới `display_timezone`. `value` là **chuỗi JSON** (`"Asia/Ho_Chi_Minh"`), không phải list như hai khoá cũ. | DROP/ADD `ck_app_settings_key_valid`: `key IN ('current_users', 'sync_urls', 'display_timezone')` | Upgrade: `SET LOCAL lock_timeout = '5s'`, drop rồi add CHECK (bảng vài dòng, quét tức thì). Downgrade: `DELETE FROM app_settings WHERE key = 'display_timezone'` **trước**, rồi drop/add CHECK cũ. Mất lựa chọn múi giờ, hệ thống về env. |
| `tasks` | Thêm `due_all_day BOOLEAN NOT NULL DEFAULT false` | CHECK `ck_tasks_due_all_day_midnight`: `NOT due_all_day OR (due_at IS NOT NULL AND (due_at AT TIME ZONE 'UTC')::time = '00:00')`. **Không** thêm index (xem 2.3). | Upgrade: add column (PG ≥ 11 chỉ đổi metadata), backfill một `UPDATE` (2.2), rồi add CHECK. Downgrade: drop CHECK, drop column. `due_at` không đổi giá trị nên downgrade không mất hạn, chỉ quay về quy tắc quá hạn cũ. |

### 2.2. Backfill `due_all_day`

```sql
UPDATE tasks
SET due_all_day = true
WHERE source = 'jira'
  AND due_at IS NOT NULL
  AND (due_at AT TIME ZONE 'UTC')::time = '00:00';
```

Lý do heuristic này đúng: cả hai đường sync Jira (Python `_parse_due` và TS `jira-actions.ts`) đều chỉ sinh `00:00 UTC` từ `duedate`, và Jira Cloud không có giờ cho `duedate`. Áp cả cho task trong thùng rác (không lọc `deleted_at`) để phục hồi ra vẫn đúng. Task `manual` không bị đụng. Rủi ro dương tính giả: R5.

db-reviewer cần xác nhận: biểu thức `AT TIME ZONE 'UTC'` trong CHECK chạy được trên bản Postgres đang dùng. Nếu không, bỏ CHECK ở DB và giữ ràng buộc ở Pydantic + service (ghi rõ trong migration).

### 2.3. Không thêm index

Điều kiện quá hạn mới là `OR` của hai nhánh trên cùng cột `due_at`, vẫn dùng được `ix_tasks_due_at`. Bảng cỡ nghìn dòng; thêm index cho cột boolean không có lợi.

### 2.4. Mã nguồn cho backend-dev

**Enum** (`models/enums.py`): thêm `DISPLAY_TIMEZONE = "display_timezone"` vào `SettingKey`. `_KEY_CHECK` ở `models/app_setting.py` tự sinh lại từ enum, nhưng **migration phải viết tay** (`alembic check` không so CHECK). Sửa docstring `AppSetting` ("`value` hiện tại luôn là list[str]") thành mô tả đúng.

**Model** (`models/task.py`): thêm

```python
# Hạn là CẢ NGÀY (Jira `duedate`): `due_at` khi đó luôn là 00:00 UTC của ngày lịch, và
# quá hạn tính theo NGÀY ở múi giờ người dùng, không theo giờ. Xem clock.py.
due_all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=sa.false())
```

kèm `CheckConstraint` cùng tên với migration.

## 3. API contract

Mọi route nằm dưới `/api/v1`, yêu cầu `X-API-Key` (router cha). Thêm vào `api/v1/settings.py`. Route tĩnh, không xung đột với route động nào.

| Method | Path | Request | Response | Lỗi |
|---|---|---|---|---|
| GET | `/settings/display-timezone` | không | `DisplayTimezoneRead` | 401 |
| PUT | `/settings/display-timezone` | `DisplayTimezoneBody` | `DisplayTimezoneRead` | 401; 422 tên không hợp lệ; 409 đang có lần nhập giữ khoá ghi (cùng cơ chế `take_import_write_lock` như `current-users`) |
| GET | `/settings/timezones` | không | `TimezoneList` | 401 |
| GET | `/system/info` | không | `SystemInfo`: `display_timezone` nay là **giá trị hiệu lực**; thêm `display_timezone_default` | 401 |
| GET | `/tasks`, `/tasks/{id}`, `/tasks/agenda` | không đổi | `TaskRead` thêm `due_all_day: bool` (bắt buộc, không default); `is_overdue` theo quy tắc mới | không đổi |
| POST | `/tasks/upsert-batch` | `TaskUpsert` thêm `due_all_day: bool \| None = None` | không đổi | 422 nếu `due_all_day=true` mà `due_at` null hoặc không phải đúng `00:00:00` UTC |

### 3.1. Pydantic (`schemas/settings.py`)

```python
class DisplayTimezoneBody(BaseModel):
    # null = xoá dòng setting, quay về mặc định env.
    timezone: str | None = Field(default=None, max_length=64)
    # validator: strip; khác None thì phải qua normalize_timezone(), trả tên chuẩn.

class DisplayTimezoneRead(BaseModel):
    timezone: str          # giá trị hiệu lực
    default: str           # env DISPLAY_TIMEZONE
    source: Literal["setting", "default"]

class TimezoneOption(BaseModel):
    name: str              # "Asia/Ho_Chi_Minh"
    utc_offset_minutes: int  # offset TẠI THỜI ĐIỂM gọi (DST làm thay đổi), chỉ để hiển thị

class TimezoneList(BaseModel):
    items: list[TimezoneOption]   # sắp theo name
    total: int
```

`normalize_timezone(value: str) -> str`: tên phải thuộc `zoneinfo.available_timezones()` (tính một lần, cache module-level), loại `Factory` và `localtime`; dài tối đa 64; không chứa ký tự điều khiển. Dùng chung cho API, đường nhập JSON và validator env.

`/settings/timezones` **không phân trang**: đây là danh mục tĩnh khoảng 600 tên (dưới 25 KB), không phải dữ liệu người dùng tăng dần, nên không thuộc quy tắc 50 dòng/trang của AGENTS.md mục 3.5. Ghi lý do này trong docstring route.

### 3.2. Đọc múi giờ lúc chạy (`services/clock.py`)

```python
def display_tz() -> ZoneInfo: ...
    # Thứ tự: ContextVar của request -> cache tiến trình còn hạn -> ZoneInfo(settings.display_timezone).
    # Giữ nguyên chữ ký đồng bộ: is_overdue (computed field) và _to_utc gọi từ chỗ không có session.

async def load_display_tz(session: AsyncSession) -> ZoneInfo: ...
    # Đọc app_settings (PK lookup) nếu cache hết hạn, đặt ContextVar cho request hiện tại.

def invalidate_display_tz_cache() -> None: ...
    # Gọi sau khi PUT thành công (chỉ có tác dụng ở worker đang xử lý request).

def today_all_day_cutoff(today: date) -> datetime: ...
    # datetime.combine(today, time.min, tzinfo=UTC): task cả ngày quá hạn khi due_at < mốc này.
```

- **Cache:** module-level, TTL **10 giây** (Q3). Prod chạy `uvicorn --workers 2` (`apps/core/Dockerfile:44`), nên worker kia có thể dùng giá trị cũ tối đa 10 giây sau khi đổi. Chấp nhận được với setting đổi hiếm.
- **ContextVar:** một dependency `async def` (`api/deps.py::bind_display_tz`) gắn vào router v1 gọi `load_display_tz`, để trong **một request** mọi phép tính (agenda, stats, `is_overdue` lúc serialize) dùng cùng một múi giờ. Phải là `async def`: dependency đồng bộ chạy trong threadpool, ContextVar đặt ở đó không truyền về request.
- **Tác vụ ngoài request** (Jira sync nếu chạy nền, purge): gọi `load_display_tz(session)` ở đầu tác vụ.
- **Giá trị DB hỏng** (dòng sửa tay, tên bị tzdata gỡ): log cảnh báo một dòng, rơi về env. Không làm vỡ request.
- **Validate env lúc khởi động:** thêm `field_validator` cho `Settings.display_timezone` dùng `normalize_timezone`, sai thì app không lên (fail fast).

**Thay mọi chỗ đọc thẳng env:**

| Vị trí | Sửa thành |
|---|---|
| `task_service.get_stats` ~580 `func.timezone(settings.display_timezone, ...)` | `func.timezone(clock.display_tz().key, ...)` |
| `api/v1/system.py:27` | giá trị hiệu lực (`await clock.load_display_tz(session)`), thêm `display_timezone_default=settings.display_timezone` |
| `schemas/system.py` | thêm field `display_timezone_default: str` |
| `task_sync_service._to_utc` ~210 | không đổi code (đã qua `clock`), chỉ sửa docstring |

Kiểm lại bằng `grep -rn "settings.display_timezone" apps/core/app`: sau epic chỉ còn trong `clock.py`, `config.py`, `api/v1/system.py` (field default), `api/v1/settings.py`.

### 3.3. Quy tắc quá hạn và agenda

Gọi `now = now_utc()`, `today = local_today()`, `cutoff = today_all_day_cutoff(today)`.

| Khái niệm | Task có giờ (`due_all_day = false`) | Task cả ngày (`due_all_day = true`) |
|---|---|---|
| Quá hạn | `due_at < now` | `due_at < cutoff` (ngày hạn < hôm nay local) |
| Sắp đến hạn (7 ngày) | `now <= due_at < now + 7d` | `cutoff <= due_at < cutoff + 7d` (gồm cả hạn hôm nay) |

- Một helper SQL duy nhất trong `task_service.py`: `_overdue_clause(now, cutoff)` và `_due_soon_clause(now, cutoff)`, dùng ở `get_agenda.overdue`, `get_agenda.due_soon`, `get_stats.overdue_total`. Không chép điều kiện ra nhiều chỗ.
- `TaskRead.is_overdue`: nhánh `due_all_day` so `self.due_at.astimezone(UTC).date() < clock.local_today()`.
- **Hệ quả cần nói với User:** task hạn hôm nay chuyển từ nhóm "Quá hạn" sang "Sắp đến hạn" trên trang Hôm nay.

### 3.4. Jira sync

- `jira_mapping._parse_due`: giữ cách lưu `00:00 UTC`, và `build_task_upsert` gửi thêm `due_all_day=True` khi có hạn. Sửa comment dòng 139 và khối comment cuối file (dòng 309, 321-327).
- **Jira bỏ hạn** (trước có, nay không): gửi `due_at=None, due_all_day=False` tường minh (hiện tại không gửi gì). Chỉ có tác dụng nếu qua được điều kiện dưới.
- **Cập nhật hạn có điều kiện** (khuyến nghị, Q4 phương án C): bỏ `due_at` khỏi `CREATE_ONLY`, thêm khái niệm `SYNC_IF_UNCHANGED = {"due_at"}` trong `task_sync_service.upsert`:
  - Lấy "giá trị sync lần trước" = `_parse_due(existing.raw_payload["fields"]["duedate"])` (raw_payload đã lưu `duedate` theo allowlist, `jira_mapping.build_raw_payload`).
  - Nếu `existing.due_at` (và `due_all_day`) khớp giá trị đó, hoặc `existing.due_at` là null: ghi hạn mới, ghi `task_event` như mọi thay đổi trường khác.
  - Nếu không khớp (User đã sửa tay) hoặc raw_payload cũ không có thông tin: **giữ nguyên**, thêm một `SyncMessage` mức info "giữ hạn sửa tay" (đếm gộp, không liệt kê nội dung Jira).
  - Thứ tự bắt buộc: so sánh với raw_payload **cũ** trước khi raw_payload bị ghi đè bằng bản mới trong cùng lần upsert.
- Các trường khác trong `CREATE_ONLY` (`priority`, `assignee`, `project_key`) **không đổi**.

### 3.5. Nhập JSON (`import_service.py`, `schemas/imports.py`)

- `SUPPORTED_DATAFILE_VERSION` 6 → 7, vẫn nhận 6. File < 7 thiếu `due_all_day`: áp cùng heuristic 2.2 khi nhập.
- Envelope nhận thêm `display_timezone: str | None` tuỳ chọn (cài đặt, cùng nhóm `current_users`/`sync_urls`). Validate bằng `normalize_timezone`; sai thì báo issue và bỏ qua khoá đó, không làm hỏng cả lần nhập. Cần hàm ghi giá trị vô hướng: thêm `settings_service.put_value(session, key, value: Any)` dùng chung câu upsert với `put_list` (đổi `put_list` thành gọi `put_value`).

## 4. Thay đổi Web

### 4.1. Nguồn múi giờ

- `lib/api.ts`:
  - `getDisplayTimezoneApi(): Promise<DisplayTimezoneRead>` bọc bằng `cache()` của React để một lần render chỉ gọi một lần. Chế độ file/memory: đọc `engine.getDisplayTimezone()`. **Lỗi mạng/API sập: trả dự phòng** `{timezone: process.env.NEXT_PUBLIC_DISPLAY_TZ ?? "Asia/Ho_Chi_Minh", source: "default"}` để layout không bao giờ vỡ.
  - `setDisplayTimezoneApi(tz: string | null)`, `listTimezonesApi()`. Chế độ file: danh sách từ `Intl.supportedValuesOf("timeZone")` chạy trên server.
- `lib/store/engine.ts`: `getDisplayTimezone()`/`setDisplayTimezone()` đọc/ghi `meta.display_timezone`, validate bằng `new Intl.DateTimeFormat("en", { timeZone })` trong try/catch. Hai chỗ dùng `DISPLAY_TZ` (60, 606) đổi sang `getDisplayTimezone()`.

### 4.2. Format và hydrate

- `lib/format.ts`: **xoá export `DISPLAY_TZ`.** Mọi hàm nhận tham số `tz: string` bắt buộc: `formatDateTime(iso, tz)`, `formatPlainDate(value, tz)`, `formatFullPlainDate(value, tz)`, `todayInDisplayTz(tz)`. Formatter cache theo `tz` trong một `Map` để không tạo `Intl.DateTimeFormat` mỗi lần gọi. Thêm:
  - `formatDue(task, tz)`: `due_all_day` thì hiển thị ngày thuần từ `due_at.slice(0, 10)` (ngày UTC chính là ngày lịch, **không** quy đổi múi giờ), ngược lại `formatDateTime`.
  - `zonedLocalToUtcIso(local: string, tz: string): string`: đổi chuỗi `datetime-local` theo múi giờ đã chọn sang ISO UTC. Thay cho `new Date(dueLocal)` ở `quick-add-form.tsx:58` (hiện quy đổi theo múi giờ **browser**, sai khi browser khác múi giờ đã chọn).
- `lib/timezone-context.tsx` (mới, `"use client"`): `TimezoneProvider({ tz, children })` và `useDisplayTz()`; ném lỗi rõ ràng nếu dùng ngoài provider.
- `app/layout.tsx`: Server Component gọi `getDisplayTimezoneApi()` và bọc toàn app trong `<TimezoneProvider tz=...>`. Server và client nhận **cùng một chuỗi** tz, nên không có hydration mismatch.
- Client component dùng `useDisplayTz()`: `task-item.tsx`, `trash-item.tsx`, `note-item.tsx`, `trash-note-item.tsx`, `jira-connections-manager.tsx`, `quick-add-form.tsx`. Server Component (`app/page.tsx`) lấy tz qua `getDisplayTimezoneApi()`.
- Kiểm bằng `grep -rn "DISPLAY_TZ" apps/web --include=*.ts --include=*.tsx`: sau epic chỉ còn trong `lib/api.ts` (giá trị dự phòng).

### 4.3. Route / trang

- `/data`, mục "Cài đặt" (cạnh `CurrentUserManager`): component mới `components/timezone-picker.tsx` (`"use client"`): ô tìm có `<datalist>` từ `listTimezonesApi()`, hiện offset hiện tại và "Hôm nay theo múi giờ này: ...", nút Lưu và nút "Dùng mặc định (`<default>`)". Lỗi hiện tại chỗ, không `alert`.
- `/system`, mục Cấu hình: dòng múi giờ hiện `display_timezone` (hiệu lực), `display_timezone_default` và nhãn nguồn; kèm link "Đổi ở trang Dữ liệu". Chỉ đọc, đúng quy ước `/system` không có thao tác ghi.
- Không thêm trang mới, không sửa `lib/nav.ts`.

### 4.4. Server Action

`app/actions-user.ts` thêm:

```ts
/** Lưu múi giờ hiển thị. null = về mặc định env. Validate sơ bộ ở đây vì Server Action là
 *  endpoint công khai; backend là nơi quyết định cuối (danh sách IANA). */
export async function setDisplayTimezoneAction(tz: string | null): Promise<SetUsersResult>
```

Validate: `null` hoặc string, dài 1..64, khớp `/^[A-Za-z0-9_+\-\/]+$/`. Lỗi `CoreApiError` trả message của backend. Thành công: `revalidatePath("/", "layout")` vì layout giữ tz.

### 4.5. Chế độ file

- `lib/store/types.ts`: `SCHEMA_VERSION` 6 → 7; `meta.display_timezone?: string`; task thêm `due_all_day: boolean`.
- `lib/store/json-file.ts`: bước migrate 6 → 7 backfill `due_all_day` theo cùng heuristic 2.2 (`source === "jira"` và `due_at` kết thúc bằng `T00:00:00.000Z` hoặc `T00:00:00Z`); chạy cả khi khôi phục file cũ.
- `engine.ts`: quy tắc quá hạn/sắp đến hạn như bảng 3.3 ở ba chỗ (511, 559-573, 652), gom về một helper.
- `app/jira-actions.ts`: đặt `due_all_day: true` khi có `duedate`; cập nhật hạn có điều kiện như 3.4 (so với `raw_payload` cũ của task).
- `lib/store/transfer.ts`, `lib/store/csv.ts`: xuất/nhập thêm `due_all_day` và `display_timezone`.

### 4.6. Types

Sau khi backend xong: `make gen-types` sinh lại `lib/generated/openapi.d.ts`. `lib/types.ts` alias `DisplayTimezoneRead`, `TimezoneOption`, `TimezoneList`. Không viết tay field.

## 5. Ownership (không agent nào sửa file của agent khác)

Thứ tự: backend-dev xong và chạy `make gen-types` trước; frontend-dev bắt đầu sau (hoặc song song theo contract mục 3 trong worktree riêng, rồi sinh lại types khi backend merge).

- **backend-dev:**
  - `apps/core/app/models/enums.py`, `models/app_setting.py`, `models/task.py`
  - `apps/core/migrations/versions/<mới>_user_timezone_due_all_day.py`
  - `apps/core/app/core/config.py` (validator)
  - `apps/core/app/services/clock.py`, `settings_service.py`, `task_service.py`, `task_sync_service.py`, `integration_sync_service.py`, `jira_mapping.py`, `import_service.py`
  - `apps/core/app/schemas/settings.py`, `schemas/task.py`, `schemas/task_upsert.py`, `schemas/system.py`, `schemas/imports.py`
  - `apps/core/app/api/deps.py`, `api/v1/settings.py`, `api/v1/system.py`, `api/v1/router.py` (gắn dependency)
  - `apps/core/tests/**`
  - `scripts/smoke-test.sh`
- **frontend-dev:**
  - `apps/web/lib/format.ts`, `lib/timezone-context.tsx` (mới), `lib/api.ts`, `lib/types.ts`, `lib/generated/openapi.d.ts` (chỉ qua `make gen-types`)
  - `apps/web/lib/store/engine.ts`, `lib/store/types.ts`, `lib/store/json-file.ts`, `lib/store/transfer.ts`, `lib/store/csv.ts`
  - `apps/web/app/layout.tsx`, `app/page.tsx`, `app/data/page.tsx`, `app/system/page.tsx`, `app/actions-user.ts`, `app/jira-actions.ts`
  - `apps/web/components/timezone-picker.tsx` (mới), `task-item.tsx`, `trash-item.tsx`, `note-item.tsx`, `trash-note-item.tsx`, `jira-connections-manager.tsx`, `quick-add-form.tsx`
- **orchestrator:**
  - `docs/specs/user-timezone.md` (đổi trạng thái khi User chốt), `docs/AI_HANDOFF_STATE.md`, `apps/web/lib/docs.ts` (đăng ký spec)
  - `docs/API_REFERENCE.md`, `docs/huong-dan-su-dung.md` (dòng ~353 về `NEXT_PUBLIC_DISPLAY_TZ`), `docs/deploy-runbook.md` (~171), `docs/PROXMOX_DEPLOY.md` (~390, ~459), `docs/specs/proxmox-deploy.md` (~111)
  - `.agents/rules/backend-conventions.md` (dòng 24: đổi `settings.display_timezone` thành `clock.display_tz().key`; thêm quy tắc quá hạn cả ngày), `.agents/rules/web-conventions.md` (format nhận `tz` tường minh, `NEXT_PUBLIC_DISPLAY_TZ` chỉ là dự phòng, `SCHEMA_VERSION` v7), `.agents/rules/ops.md` (bản đồ code: `clock.py`, `timezone-context.tsx`)

## 6. Tiêu chí nghiệm thu (kiểm chứng được)

- [ ] `make migrate` lên head mới; `make psql` rồi `\d tasks` thấy `due_all_day` và `ck_tasks_due_all_day_midnight`; `\d app_settings` thấy CHECK có 3 khoá.
- [ ] Downgrade một bước rồi upgrade lại chạy sạch (`alembic downgrade -1 && alembic upgrade head` trong container api), có dòng `display_timezone` trong bảng trước khi downgrade.
- [ ] Sau backfill: `SELECT count(*) FROM tasks WHERE source='jira' AND due_at IS NOT NULL AND NOT due_all_day` trả số task Jira có hạn **không** phải 00:00 UTC (kỳ vọng 0 với dữ liệu hiện tại).
- [ ] `make lint` pass; `grep -rn "settings.display_timezone" apps/core/app` chỉ còn các file nêu ở 3.2.
- [ ] pytest (`apps/core/tests`) pass, có test mới:
  - `test_clock.py`: `display_tz()` theo thứ tự ContextVar → cache → env; cache hết hạn sau TTL (giả `time.monotonic`); giá trị DB hỏng rơi về env; `local_day_bounds_utc` đúng với `Pacific/Kiritimati` (+14) và `Etc/GMT+12` (-12); ngày chuyển DST (`America/New_York`, 2026-03-08 và 2026-11-01) cho khoảng 23h/25h.
  - `test_settings.py`: sửa assertion dòng 266 và 701 thành 3 khoá; PUT hợp lệ/không hợp lệ (`"Mars/Base"`, `"Factory"`, chuỗi 65 ký tự) → 200/422; PUT `null` xoá dòng, GET trả `source="default"`.
  - Quá hạn: task cả ngày hạn hôm nay (local) → `is_overdue=false`, có trong `due_soon`, không trong `overdue`, không tính vào `overdue_total`; hạn hôm qua → quá hạn; task có giờ giữ hành vi cũ. Chạy với hai múi giờ +14/-12 để bắt lỗi lệch ngày.
  - Jira sync: hạn đổi trên Jira và User chưa sửa → cập nhật + có `task_event`; User đã sửa tay → giữ nguyên + có message; Jira bỏ hạn và User chưa sửa → `due_at=null, due_all_day=false`; raw_payload cũ thiếu `duedate` → giữ nguyên.
  - Nhập JSON v6 (không `due_all_day`) → backfill đúng; v7 có `display_timezone` hợp lệ → được ghi; không hợp lệ → issue, phần còn lại vẫn nhập.
- [ ] `make smoke` pass, có assertion mới: đọc múi giờ ban đầu và **khôi phục ở cuối kể cả khi lỗi** (`trap`); PUT `Pacific/Kiritimati` rồi `Etc/GMT+12`, `reference_date` của `/tasks/agenda` khác nhau giữa hai lần (hai múi giờ lệch 26 giờ nên luôn khác ngày); PUT tên rác → 422; upsert-batch một task `due_all_day=true` hạn hôm nay theo múi giờ hiện hành → `is_overdue=false`; `due_all_day=true` với `due_at` 10:00Z → 422.
- [ ] `cd apps/web && npx tsc --noEmit` pass; `npm run lint` pass; `grep -rn "DISPLAY_TZ" apps/web --include=*.ts --include=*.tsx` chỉ còn `lib/api.ts`.
- [ ] Kịch bản tay (chế độ api): ở `/data` đổi sang `America/New_York`, trang Hôm nay đổi ngày tiêu đề (nếu đang qua nửa đêm một bên), giờ ở task đổi theo, console browser **không** có cảnh báo hydration; `/system` hiện giá trị hiệu lực và mặc định; "Dùng mặc định" trả về `Asia/Ho_Chi_Minh`.
- [ ] Kịch bản tay: task Jira hạn hôm nay hiện "Hạn: T5, 09/10" (không giờ), nằm ở "Sắp đến hạn", không đỏ quá hạn lúc sau 07:00 sáng.
- [ ] Kịch bản tay: đặt browser (DevTools > Sensors) sang `Europe/London`, múi giờ app vẫn `Asia/Ho_Chi_Minh`, QuickAdd hạn 17:00 → task hiện 17:00 (không phải 23:00).
- [ ] Kịch bản tay chế độ file (`make use-local`): file v6 nạp lên thành v7, đổi múi giờ lưu vào `meta`, quá hạn theo quy tắc mới.

## 7. Rủi ro & quyết định

### 7.1. Rủi ro

- **R1. "Hôm nay" dịch khi đổi múi giờ.** `completed_today`, `minutes_logged_today`, `completed_last_7_days`, tiêu đề trang Hôm nay tính lại theo múi giờ mới ngay lập tức. `scheduled_for` là ngày thuần nên **không** dịch: một task lên lịch "hôm nay" có thể thành "hôm qua" nếu đổi sang múi giờ đang ở ngày khác. Đây là đúng ngữ nghĩa, ghi trong hướng dẫn sử dụng; UI picker hiện "Hôm nay theo múi giờ này" trước khi lưu.
- **R2. Dữ liệu cũ không viết lại.** `due_at` của task có giờ là thời điểm tuyệt đối, đổi múi giờ chỉ đổi cách hiển thị, không cần migrate. Task cả ngày lưu theo ngày UTC chuẩn nên cũng không cần. Naive datetime đã nhập trước đây (`_to_utc`) đã được quy đổi theo múi giờ lúc nhập; đổi múi giờ sau không sửa lại chúng.
- **R3. Hai worker, cache 10 giây.** Sau PUT, worker kia có thể trả kết quả theo múi giờ cũ tối đa 10 giây. Nếu không chấp nhận: đọc DB mỗi request (thêm một PK lookup, khoảng dưới 1 ms) hoặc khoá phiên bản qua Redis (Q3).
- **R4. Hydration.** Nếu một client component nào còn tự tạo `Intl.DateTimeFormat` không có `timeZone`, server (UTC trong container) và browser sẽ lệch. Tiêu chí grep ở mục 6 chặn việc này; code-reviewer phải rà thêm `toLocale*String(` không truyền `timeZone`.
- **R5. Backfill dương tính giả.** Task Jira mà ai đó sửa tay hạn thành đúng `07:00` giờ VN (= 00:00 UTC) sẽ bị coi là cả ngày. Xác suất thấp, hậu quả nhẹ (quá hạn trễ hơn vài giờ).
- **R6. Nhập Excel/URL chưa gửi `due_all_day`.** Hạn từ Excel vẫn theo quy tắc có giờ, có thể còn hiện tượng quá hạn sớm với nguồn này. Ngoài phạm vi, ghi vào handoff.
- **R7. Ghi đè hạn sửa tay.** Phương án C dựa vào `raw_payload` lần trước. Trước epic `due_at` là CREATE_ONLY còn raw_payload bị ghi đè, nên task Jira cũ có hạn lệch `raw_payload.fields.duedate` và sẽ bị hiểu nhầm là "User sửa tay" (kẹt hạn cũ). Xử lý: migration `a1c9e4b7d2f8` có bước đối soát SAU backfill `due_all_day`, TRƯỚC CHECK: với task Jira `due_all_day` mà `duedate` hợp lệ, đặt lại `due_at` = 00:00 UTC của `duedate` (hạn 00:00 UTC cũ do sync sinh ra nên chưa ai sửa tay; Jira đã bỏ hạn thì giữ nguyên). Đường chống kẹt về sau: khi `raw_payload` của lần sync bị bỏ (PayloadDropped) thì baseline không làm mới được, nên `_resolve_due` hoãn việc đổi hạn tới lần sync có payload (không ghi hạn, không đếm là sửa tay).
- **R8. tzdata.** Danh sách IANA phụ thuộc tzdata của image (`zoneinfo` dùng tzdata hệ thống). Khuyến nghị thêm gói Python `tzdata` vào `pyproject.toml` để danh sách cố định theo lock file, không theo base image (Q5).
- **R9. File JSON v7.** File xuất từ bản mới không mở được ở web bản cũ (v6). Bình thường với mọi lần tăng `SCHEMA_VERSION`.

### 7.2. Phương án cho hạn cả ngày (đã chọn B)

| Phương án | Cách làm | Ưu | Nhược |
|---|---|---|---|
| A | Lưu Jira `duedate` thành 23:59:59.999 giờ local, giữ `due_at < now` | Không đổi schema, không đổi query | Đổi múi giờ sau đó làm hạn lệch ngày (phải viết lại dữ liệu); hiển thị "23:59" khó hiểu; backfill phụ thuộc múi giờ lúc chạy migration |
| **B (chọn)** | Cột `due_all_day`, lưu 00:00 UTC của ngày lịch, so theo ngày local | Đúng khi đổi múi giờ; hiển thị ngày thuần; tách bạch hai loại hạn | Thêm cột, migration, `SCHEMA_VERSION` 7, điều kiện SQL hai nhánh |
| C | Không thêm cột, đoán "00:00 UTC + source jira = cả ngày" lúc đọc | Không migration | Heuristic chạy mãi mãi ở mọi query; sai với task tay lúc 07:00 VN; khó kiểm |

### 7.3. Phương án cập nhật hạn từ Jira (Q4)

| Phương án | Hành vi | Đánh đổi |
|---|---|---|
| A. Giữ create-only (hiện tại) | Không bao giờ cập nhật hạn | An toàn cho hạn sửa tay; hạn lệch Jira mãi mãi, đúng lỗi User đang gặp |
| B. Luôn ghi đè | Jira là chủ của hạn | Đơn giản; mất hạn User sửa tay mỗi lần sync |
| **C. Ghi đè nếu User chưa sửa (khuyến nghị)** | So với `raw_payload.fields.duedate` lần trước | Đúng cả hai nhu cầu, không thêm cột; logic phức tạp hơn, cần test kỹ; task cũ thiếu raw_payload cập nhật trễ một lần sync |
| D. Cột `due_at_overridden` | Đánh dấu tường minh khi User PATCH hạn | Rõ ràng nhất; thêm cột và phải đặt cờ ở mọi đường ghi tay (PATCH, nhập file) |

## Câu hỏi cần User chốt

1. **Q1. Nơi đặt bộ chọn múi giờ:** `/data` (cạnh "Tên của tôi", nơi đã có cài đặt) và `/system` chỉ hiển thị. Khuyến nghị: **đồng ý**. Muốn đặt ở `/system` thì trang đó sẽ có thao tác ghi đầu tiên.
2. **Q2. Hạn Jira cả ngày (cột `due_all_day`, quá hạn khi ngày hạn < hôm nay local):** Khuyến nghị **phương án B** (mục 7.2). Hệ quả: task hạn hôm nay chuyển từ "Quá hạn" sang "Sắp đến hạn".
3. **Q3. Độ trễ khi đổi múi giờ với 2 worker:** cache 10 giây, hay đọc DB mỗi request? Khuyến nghị: **cache 10 giây**.
4. **Q4. Sync cập nhật hạn từ Jira:** Khuyến nghị **C** (ghi đè nếu User chưa sửa tay). Chọn B nếu Jira luôn là nguồn đúng và bạn không bao giờ sửa hạn ở đây.
5. **Q5. Thêm gói Python `tzdata` để cố định danh sách múi giờ?** Khuyến nghị: **có** (`make lock`, `make build`).
6. **Q6. `NEXT_PUBLIC_DISPLAY_TZ`:** giữ làm dự phòng khi API sập (epic này), gỡ hẳn ở epic sau? Khuyến nghị: **giữ làm dự phòng**.
7. **Q7. Chế độ file cũng làm đủ (SCHEMA_VERSION 7, quy tắc quá hạn mới, cập nhật hạn có điều kiện)?** Khuyến nghị: **có**, để hai chế độ không cho kết quả khác nhau. Nếu muốn nhỏ lại: chế độ file chỉ làm phần múi giờ, phần hạn để epic sau.

## Phụ lục A. Điểm lệch giữa tài liệu và code

1. Docstring `AppSetting` ghi "`value` hiện tại luôn là list[str]": sẽ sai khi thêm `display_timezone` (chuỗi). Sửa trong epic.
2. `.agents/rules/backend-conventions.md` dòng 24 hướng dẫn `func.timezone(settings.display_timezone, ...)`: phải đổi sau epic, nếu không agent sau sẽ đưa lại cách đọc env.
3. `quick-add-form.tsx:55-58` comment nói "quy đổi bằng Date của browser để gửi lên ISO có offset đúng": chỉ đúng khi múi giờ browser trùng múi giờ hiển thị. Sửa trong epic (4.2).
4. `docs/specs/proxmox-deploy.md` (dòng ~111) và `docs/PROXMOX_DEPLOY.md` (~459) nói múi giờ cố định lúc build: sau epic múi giờ chỉnh được lúc chạy, `NEXT_PUBLIC_DISPLAY_TZ` chỉ là dự phòng.
5. Comment `docker-compose.prod.yml:10` nói "uvicorn chạy nhiều worker", khớp `apps/core/Dockerfile:44` (`--workers 2`): đây là lý do cần cache có TTL thay vì cache vĩnh viễn (R3).
