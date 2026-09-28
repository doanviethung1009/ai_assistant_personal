# Vận hành và bản đồ code

Trước khi làm task lớn hoặc khi bắt đầu session mới, đọc `#status` để biết
trạng thái hiện tại, phần nào đã verify và phần nào chưa.

## Đừng tự mò lệnh, đã có Makefile

Mọi thao tác đều có target. Chạy `make` để xem danh sách. Không tự viết
`docker compose ...` dài dòng, không tự đoán đường dẫn.

| Cần gì | Lệnh |
|---|---|
| Dựng stack | `make up` |
| Kiểm tra backend còn đúng | `make smoke` |
| Log | `make logs-api`, `make logs-web` |
| Migration mới | `make migration m="mô tả"` rồi `make migrate` |
| Lint và typecheck | `make lint` |
| Vào DB | `make psql` |
| Đổi dependency Python | sửa `pyproject.toml`, `make lock`, `make build` |

Không chạy `npm run dev` hay `uvicorn` trực tiếp trên host. Cả hai đã chạy
trong container với hot reload.

## Bản đồ code

```
apps/core/app/
  main.py              khởi tạo FastAPI, CORS, exception handler, lifespan
  core/config.py       Settings từ env, validate DSN phải là asyncpg
  core/security.py     require_api_key, so sánh bằng compare_digest
  core/metrics.py      middleware Prometheus, label theo route template
  core/logging.py      JSON formatter một dòng
  db/base.py           DeclarativeBase, naming convention, mixin timestamp
  db/session.py        engine async, get_session dependency (tự commit)
  db/redis.py          client redis dùng chung
  db/base.py           thêm: enum_column() — cấu hình cột enum dùng chung
  models/enums.py      TaskStatus, TaskPriority, TaskSource, TaskEventType,
                       NoteKind, NoteSource
  models/task.py       Task, TaskEvent — nơi định nghĩa constraint và index
  models/project.py    Project
  models/note.py       Note — sổ tay command/SQL/cấu hình, có soft delete
  schemas/             Pydantic, TaskRead có computed field is_overdue
  schemas/common.py    Page[T], và normalize_tags() dùng chung Task với Note
  services/
    task_service.py    toàn bộ logic nghiệp vụ của task
    project_service.py logic project
    note_service.py    logic sổ tay, gồm soft delete và mark_used
    clock.py           quy đổi "hôm nay" giữa timezone hiển thị và UTC
    errors.py          DomainError, map sang HTTP ở main.py
  api/health.py        /health/live, /health/ready — không cần API key
  api/v1/tasks.py      route tĩnh (/agenda, /stats) khai báo TRƯỚC /{task_id}
  api/v1/notes.py      route tĩnh (/trash, /stats) khai báo TRƯỚC /{note_id}
apps/web/
  lib/api.ts           duy nhất nơi gọi core API, có "server-only"
  lib/types.ts         mirror schema backend, sửa backend thì sửa cả đây
  lib/format.ts        format ngày giờ với timeZone tường minh
  lib/note-danger.ts   heuristic nhận lệnh nguy hiểm và dấu hiệu lộ secret.
                       KHÔNG "server-only": form ở client cũng gọi.
  app/actions.ts       Server Action, mọi mutation đi qua đây
  components/          task-item và quick-add-form là client component
  components/copy-button.tsx  có đường dự phòng khi navigator.clipboard
                       không tồn tại (mở app qua IP LAN không phải secure context)
```

## Quy ước dễ vi phạm

- **Route tĩnh trước route động.** Trong `api/v1/tasks.py`, `/agenda` và
  `/stats` phải khai báo trước `/{task_id}`, nếu không FastAPI khớp chuỗi
  "agenda" thành UUID và trả 422.
- **Payload của `task_events` là JSONB.** Mọi giá trị đưa vào phải qua
  `_jsonable()` trong `task_service.py`. UUID, datetime, date, Enum đều
  không tự serialize được.
- **Khái niệm "hôm nay" luôn quy đổi qua `services/clock.py`.** DB lưu UTC.
  Query nào group theo ngày phải bọc `func.timezone(settings.display_timezone, ...)`
  trước khi lấy `date()`, nếu không sẽ lệch với `reference_date`.
- **API key không được xuống browser.** Chỉ Server Component và Server Action
  gọi `lib/api.ts`. Client component gọi Server Action, không gọi fetch trực tiếp.
- **`NEXT_PUBLIC_*` nhúng lúc build**, không đọc được ở runtime. Thêm biến mới
  loại này thì phải khai báo build arg trong `apps/web/Dockerfile` và truyền
  trong `docker-compose.prod.yml`.
- **Không `create_all`.** Schema chỉ đổi qua Alembic.
- **Sửa model thì sửa cả `lib/types.ts`** và bổ sung assertion vào
  `scripts/smoke-test.sh`.
- **State của store cục bộ phải nằm trên `globalThis`.** Next bundle Server
  Component và Route Handler thành hai module graph riêng, nên biến ở mức
  module có thể tồn tại hai bản khác nhau. Triệu chứng đã gặp: trang hiển thị
  đủ dữ liệu nhưng `/api/export` trả về mảng rỗng. Xem `lib/store/engine.ts`.
- **Đọc/ghi dữ liệu chỉ qua `lib/api.ts`.** Nó điều phối ba chế độ
  `DATA_SOURCE` (api, file, memory). Đừng import `store/engine.ts` trực tiếp
  từ page hay component.
- **Thêm trang mới thì khai báo trong `lib/nav.ts`,** không sửa `layout.tsx`.
  Việc hàng ngày vào `PRIMARY_NAV`, tài liệu về dự án vào `SECONDARY_NAV`.
  Nav là phẳng, không dropdown — đừng thêm lại menu bấm mới mở.
- **Sơ đồ ở `components/architecture-diagrams.tsx` tính toạ độ tay.** Giữ
  khoảng cách tối thiểu 20px giữa các hộp, cho mũi tên đi gấp khúc qua vùng
  trống. `DiagramDefs` chỉ được render một lần cho mỗi trang.
  Nhãn mũi tên **có nền nên chiếm chỗ thật**: ước lượng khoảng 6px mỗi ký tự
  rồi kiểm tra nó không chồng lên hộp nào. Đã từng phải đẩy hộp `done` từ
  x=650 sang x=680 chỉ để nhãn `completed_at` có chỗ đứng.
- **Hiệu ứng sơ đồ dùng CSS, không dùng SMIL,** để tắt được bằng
  `prefers-reduced-motion` và bằng công tắc trên trang. Khi tắt, trạng thái
  tĩnh phải là **đã vẽ xong**: nhớ reset `stroke-dasharray` trong khối
  `[data-motion="off"]`, nếu không nét sẽ biến mất. Chỉ bật `animated` cho
  luồng chính, đừng cho mọi mũi tên chạy cùng lúc.
- **Thêm tài liệu mới thì khai báo trong `lib/docs.ts`** và mount vào compose
  nếu file nằm ngoài `apps/web`. Tài liệu người dùng ở `docs/`.
- **Xoá task là xoá mềm.** Mọi truy vấn nghiệp vụ phải lọc `deleted_at IS NULL`
  (backend dùng helper `_alive()`, web dùng `aliveTasks()`). Thiếu nó là task
  trong thùng rác lại hiện ở agenda và thống kê.
- **Ràng buộc unique phải là partial index.** `UNIQUE (source, external_id)` có
  điều kiện `WHERE deleted_at IS NULL`. Áp dụng cho cả `tasks` và `notes`. Bản
  ghi xoá mềm không được chiếm chỗ, nếu không thì sync lại từ Jira hay Obsidian
  sẽ bị chặn.
- **Nội dung note là dữ liệu, không phải code.** `note.content` chỉ được lưu,
  trả về, và copy vào clipboard. Không đưa vào shell, không `eval`, không nối
  vào câu SQL. Khi render ở component phải dùng text node của JSX; dùng
  `dangerouslySetInnerHTML` là mở đường cho XSS vì nội dung do người dùng dán.
  Nếu sau này có tính năng "chạy note" thì nó phải là cơ chế riêng có xác nhận
  tường minh, không phải hệ quả của việc lưu note.
- **Cột enum khai báo qua `enum_column()` trong `db/base.py`.** Đừng tự gọi
  `SAEnum` với cấu hình riêng: lệch `native_enum` hay `length` giữa các bảng sẽ
  làm Alembic autogenerate sinh diff nhiễu mãi không hết.
- **Đổi cấu trúc file JSON thì phải tăng `SCHEMA_VERSION` và viết bước
  migrate.** Xem `store/json-file.ts`. Thêm field mà không backfill thì dữ liệu
  cũ đọc lên là `undefined`, và code so sánh `=== null` sẽ hiểu sai. Hiện tại
  đang ở **v3** (v2 → v3 là thêm mảng `notes`). Thêm mảng mới thì phải backfill
  thành `[]`, vì engine gọi `.filter()` ngay khi nạp.
- **Thêm entity mới thì phải đi hết chuỗi:** model → `models/__init__.py` →
  schema → service → router → `api/v1/router.py` → `lib/types.ts` →
  `store/types.ts` (`StoredX` + `DataFile`) → `store/engine.ts` →
  `lib/api.ts` (cả ba chế độ) → `app/actions.ts` → `store/csv.ts` →
  `store/transfer.ts` → `app/api/export/route.ts` → `lib/nav.ts` →
  `scripts/smoke-test.sh`. Bỏ sót một khâu thì lỗi chỉ hiện ở đúng một chế độ
  `DATA_SOURCE`, và thường là chế độ bạn không chạy lúc đó.

## Khi sửa backend

Xong thì chạy `make smoke`. Script này gọi HTTP thật, kiểm tra cả healthcheck,
xác thực, vòng đời task, agenda, stats, ràng buộc dữ liệu, và xoá dữ liệu tạm.
Nó là cách nhanh nhất để biết có làm hỏng gì không.
