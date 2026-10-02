---
inclusion: manual
---

# Trạng thái bàn giao

File này không tự nạp vào mọi request để tiết kiệm token. Gọi bằng `#status`
khi bắt đầu session mới hoặc trước khi làm task lớn.

Cập nhật lần cuối: khi chuyển project từ Windows sang Ubuntu, Phase 1.

## Đã viết xong

Backend `apps/core` — FastAPI, SQLAlchemy 2.0 async, Alembic.

- Model `Project`, `Task`, `TaskEvent`. Task đã có `source` / `external_id` /
  `raw_payload` và unique `(source, external_id)` cho sync idempotent sau này.
- REST API đầy đủ: CRUD task và project, `/tasks/agenda`, `/tasks/stats`,
  `/tasks/{id}/complete`, `/tasks/{id}/time`.
- Xác thực `X-API-Key` cho toàn bộ `/api/v1`, health và metrics mở.
- `/health/live` và `/health/ready` tách biệt, ready kiểm tra Postgres và Redis.
- `/metrics` cho Prometheus, label theo route template.
- Log JSON một dòng.

Frontend `apps/web` — Next.js App Router, Server Actions, Tailwind v4.

- Trang Hôm nay (agenda + stats), Tất cả task (tìm, lọc, phân trang), Dự án.
- Form nhập task nhanh có phần chi tiết mở rộng.
- Thao tác trên từng task: đổi status, xếp vào hôm nay, ghi thời gian, xoá có
  bước xác nhận.
- API key nằm ở server, không xuống browser.

Hạ tầng.

- `docker-compose.yml` ba profile: mặc định (postgres, redis, api, web),
  `llm` (LiteLLM), `monitoring` (Prometheus, Grafana, blackbox, các exporter).
- `docker-compose.prod.yml` override sang target prod.
- `infra/litellm/config.yaml` dùng wildcard passthrough, có budget cứng.
- `infra/monitoring/` prometheus.yml, blackbox.yml, alert rule, Grafana datasource.
- `Makefile`, `scripts/bootstrap.sh`, `scripts/gen-env.sh`, `scripts/smoke-test.sh`.

## Đã verify được

Trên máy Windows, không có Docker nên chỉ kiểm tra được ở mức tĩnh:

- `py -3 -m compileall` trên `apps/core/app` và `migrations`: pass, exit 0.
- `npm install` trong `apps/web`: thành công, 47 package.
- `npx tsc --noEmit`: pass, exit 0, không lỗi type nào.

## CHƯA verify — cần làm trước tiên trên Ubuntu

Docker Desktop trên máy Windows không khởi động được engine, nên toàn bộ phần
runtime chưa từng chạy. Việc đầu tiên trên Ubuntu:

```bash
make bootstrap
```

Bootstrap sẽ tự làm và tự báo lỗi ở đúng bước nếu sai. Những thứ chưa từng chạy:

1. **Build image** của cả `api` và `web`. Dependency Python khai báo bằng range
   trong `pyproject.toml`, `uv` sẽ tự resolve. Nếu có xung đột thì lỗi hiện ở
   bước này.
2. **Initial migration.** `migrations/versions/` hiện **trống**. Bootstrap sẽ
   sinh bằng `alembic revision --autogenerate`. Nếu bỏ qua bước này thì
   `alembic upgrade head` chạy thành công mà không tạo bảng nào, và mọi request
   sẽ lỗi. Đây là cái bẫy dễ mất thời gian nhất.
3. **Import ở runtime.** compileall chỉ bắt lỗi syntax, không bắt lỗi import
   hoặc lỗi cấu hình SQLAlchemy. Rủi ro tập trung ở `models/task.py` (constraint,
   index GIN, `SAEnum(native_enum=False)`) và `migrations/env.py`.
4. **Render của Next.js.** tsc pass không đảm bảo render đúng. Chú ý hydration
   của phần format ngày giờ.
5. **`scripts/smoke-test.sh`** chưa từng chạy. Nó tự chạy ở cuối bootstrap.

## Bug đã sửa, cần smoke test xác nhận

Hai lỗi phát hiện khi soát lại code, đã sửa nhưng chưa chạy thử:

1. `task_service.py` — payload của `TaskEvent` là JSONB nhưng diff có thể chứa
   `UUID` (project_id), `datetime` (due_at), `date` (scheduled_for). Không có
   hàm chuyển thì `json.dumps` ném TypEerror và PATCH sẽ trả 500. Đã thêm
   `_jsonable()`. Smoke test có case patch đồng thời `due_at` và `scheduled_for`
   để bắt đúng lỗi này.
2. `get_stats()` — `completed_last_7_days` group theo ngày UTC bằng
   `func.timezone("UTC", ...)`, trong khi `reference_date` là ngày địa phương.
   Lệch múi giờ làm số "xong hôm nay" trên UI sai. Đã đổi sang
   `settings.display_timezone`.

## Rủi ro đã biết, chưa xử lý

- **Chưa có rate limiting** trên core API. Redis đã sẵn, cần làm trước khi mở
  cho team.
- **Chưa có RBAC.** Hiện một API key tĩnh cho một người. Khi lên team thì thay
  `core/security.py` bằng OIDC (Authentik nhẹ hơn Keycloak cho home lab) và giữ
  nguyên chữ ký dependency để router không phải sửa.
- **`lib/types.ts` viết tay**, phải sửa song song khi đổi schema backend. Nên
  sinh tự động từ `/openapi.json` khi có thời gian.
- **Model ID trong `infra/litellm/config.yaml`** phần alias `fast` và `reasoning`
  là giá trị ví dụ, chưa xác thực. Wildcard passthrough vẫn hoạt động không cần
  sửa. Kiểm tra ID thật bằng lệnh curl ghi trong comment đầu file đó.
- **`mcp-servers/` chưa tồn tại.** Sẽ tạo ở Phase 2.

## Quyết định kiến trúc đã chốt, đừng bàn lại

- Enum lưu VARCHAR + CHECK (`native_enum=False`), không dùng native enum của
  Postgres, để thêm giá trị không phải `ALTER TYPE`.
- Sync từ nguồn ngoài dùng polling, không webhook, vì hệ thống nằm sau NAT.
- Không tự lưu metrics, query trực tiếp Prometheus.
- Postgres một node lo cả quan hệ, JSONB và pgvector. Không thêm DB thứ hai.
- Docker Compose, không Kubernetes, cho tới khi có nhu cầu thật ở home lab.
- Telegram bot là giao diện chính dự kiến cho Phase 2 vì long polling không cần
  mở port ra internet.

## Việc tiếp theo theo thứ tự

1. `make bootstrap` trên Ubuntu, sửa hết lỗi tới khi `make smoke` pass sạch.
2. Commit initial migration vừa sinh vào git.
3. `make mon-up`, xác nhận Prometheus scrape được `api:8000/metrics` và blackbox
   probe được `/health/ready`.
4. Bắt đầu Phase 2 bằng một MCP server duy nhất, chọn nguồn dùng nhiều nhất.
   Cần chốt trước: Jira Cloud hay Data Center, vì phần auth và endpoint khác nhau
   hoàn toàn. Cloud đã bỏ `/rest/api/3/search`, phải dùng `/rest/api/3/search/jql`
   với phân trang `nextPageToken`.
