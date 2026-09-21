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
  models/enums.py      TaskStatus, TaskPriority, TaskSource, TaskEventType
  models/task.py       Task, TaskEvent — nơi định nghĩa constraint và index
  models/project.py    Project
  schemas/             Pydantic, TaskRead có computed field is_overdue
  services/
    task_service.py    toàn bộ logic nghiệp vụ của task
    project_service.py logic project
    clock.py           quy đổi "hôm nay" giữa timezone hiển thị và UTC
    errors.py          DomainError, map sang HTTP ở main.py
  api/health.py        /health/live, /health/ready — không cần API key
  api/v1/tasks.py      route tĩnh (/agenda, /stats) khai báo TRƯỚC /{task_id}
apps/web/
  lib/api.ts           duy nhất nơi gọi core API, có "server-only"
  lib/types.ts         mirror schema backend, sửa backend thì sửa cả đây
  lib/format.ts        format ngày giờ với timeZone tường minh
  app/actions.ts       Server Action, mọi mutation đi qua đây
  components/          task-item và quick-add-form là client component
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
  điều kiện `WHERE deleted_at IS NULL`. Task xoá mềm không được chiếm chỗ, nếu
  không thì sync lại từ Jira sẽ bị chặn.
- **Đổi cấu trúc file JSON thì phải tăng `SCHEMA_VERSION` và viết bước
  migrate.** Xem `store/json-file.ts`. Thêm field mà không backfill thì dữ liệu
  cũ đọc lên là `undefined`, và code so sánh `=== null` sẽ hiểu sai.

## Khi sửa backend

Xong thì chạy `make smoke`. Script này gọi HTTP thật, kiểm tra cả healthcheck,
xác thực, vòng đời task, agenda, stats, ràng buộc dữ liệu, và xoá dữ liệu tạm.
Nó là cách nhanh nhất để biết có làm hỏng gì không.
