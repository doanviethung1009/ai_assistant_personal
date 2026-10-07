# Vận hành và bản đồ code

Trước khi làm task lớn hoặc khi bắt đầu session mới, đọc `docs/AI_HANDOFF_STATE.md` để biết
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
| Cài hook kiểm tra commit message | `make install-hooks` (chạy một lần) |
| Sinh lại CHANGELOG.md | `make changelog` |

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

## Quy ước dễ vi phạm — đã tách ra ngoài để đỡ tốn token

Nội dung chi tiết không còn nạp vào mọi request. Chúng nạp **đúng lúc cần**
qua frontmatter `paths:` (Claude Code, qua symlink `.claude/rules`) / `fileMatchPattern` (Kiro) — tự động theo file đang sửa hoặc qua skill (tự
động, theo mô tả việc đang làm):

| Đang làm gì | Nạp từ đâu | Kiểu nạp |
|---|---|---|
| Sửa file trong `apps/core/` | `.agents/rules/backend-conventions.md` | fileMatch |
| Sửa file trong `apps/web/` | `.agents/rules/web-conventions.md` | fileMatch |
| Viết comment/docstring (bất kỳ `.py`/`.ts`/`.tsx`/`.sh`) | `.agents/rules/comment-style.md` | fileMatch |
| Commit, viết message, chạy hook | skill `git-commit` | tự phát hiện theo mô tả |
| Thêm entity mới (model → UI → export) | skill `add-entity` | tự phát hiện theo mô tả |

Không cần gọi tay — mở đúng file hoặc nói đúng việc là đủ để agent tự nạp.
Chỉ gọi `#tên-file` khi muốn ép nạp ngoài tình huống trên.

## Khi sửa backend

Xong thì chạy `make smoke`. Script này gọi HTTP thật, kiểm tra cả healthcheck,
xác thực, vòng đời task, agenda, stats, ràng buộc dữ liệu, và xoá dữ liệu tạm.
Nó là cách nhanh nhất để biết có làm hỏng gì không.
