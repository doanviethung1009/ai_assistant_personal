# Đánh giá tổng quan — Builder AI Assistant

> Deep review toàn bộ source code (backend, frontend, infra) ngày 02-10-2026.
> Dùng để nắm bối cảnh khi tiếp tục phát triển trên macOS.

---

## 1. Tổng quan kiến trúc

```
 ┌─────────────────────────────────────────────────────────────┐
 │  Docker Compose · single node · 3 profiles                  │
 │                                                             │
 │  ┌──────────┐    Server Action    ┌──────────┐              │
 │  │ Web      │ ──────────────────▸ │ Core API │              │
 │  │ Next.js  │   API key ở server  │ FastAPI  │              │
 │  │ 15 + R19 │                     │ async    │              │
 │  └──────────┘                     └────┬─────┘              │
 │                                        │                    │
 │                        ┌───────────────┼──────────┐         │
 │                        ▼               ▼          ▼         │
 │                   ┌─────────┐   ┌──────────┐ ┌─────────┐   │
 │                   │Postgres │   │  Redis   │ │ LiteLLM │   │
 │                   │ 17+pgv  │   │  7.4     │ │ Gateway │   │
 │                   └─────────┘   └──────────┘ └─────────┘   │
 │                                                             │
 │  Profile monitoring:  Prometheus ◂── Blackbox               │
 │                       Grafana, cadvisor, node-exporter      │
 └─────────────────────────────────────────────────────────────┘
```

Monorepo gồm 2 app chính + hạ tầng, tổng ~8.500 dòng code:

| Thành phần | Công nghệ | Dòng code | Files |
|---|---|---|---|
| Backend API | Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic | ~2.200 | 20 |
| Frontend | Next.js 15, React 19, TypeScript strict, Tailwind v4 | ~1.400 (+2.600 store) | ~25 |
| Infra & Scripts | Docker Compose, Makefile 316 dòng, bash scripts | ~3.700 | 23 |
| Tài liệu | Steering, skills, docs, README | ~1.200 | 12 |

---

## 2. Điểm mạnh nổi bật

### A. Thiết kế kiến trúc chắc chắn

- **Task model đa nguồn từ đầu**: `source`, `external_id`, `raw_payload` với
  partial unique index `WHERE deleted_at IS NULL`. Phase 2 thêm Jira/Calendar
  không cần migrate dữ liệu, chỉ cần thêm giá trị enum.
- **3 chế độ DATA_SOURCE** (`api` / `file` / `memory`): demo không cần
  Postgres, phát triển UI không cần backend. Cả 3 chế độ chia sẻ interface
  trong `lib/api.ts`.
- **API key không chạm browser**: Server Component + Server Action gọi
  `lib/api.ts` (có `import "server-only"`). Client component gọi qua Server
  Action, không bao giờ fetch trực tiếp.
- **LLM qua gateway**: LiteLLM với alias mục đích (`fast` → Gemini Flash-Lite,
  `reasoning` → Claude Sonnet). Wildcard passthrough cho mọi provider. Budget
  cap cứng $20/30 ngày — vượt là chặn.
- **Soft delete nhất quán**: `deleted_at` + partial unique index + `_alive()`
  helper. Bản ghi xoá mềm không chiếm slot unique constraint → sync lại từ
  nguồn ngoài vẫn hoạt động.

### B. Code quality cao

Backend — file lớn nhất `task_service.py` (611 dòng) được tổ chức tốt:

- Async xuyên suốt, type hint đầy đủ, ruff + mypy configured.
- `_jsonable()` xử lý UUID/datetime/date/Enum → JSONB an toàn.
- `_priority_rank()` case expression cho sort theo priority weight.
- `get_stats()` dùng `func.timezone(settings.display_timezone, ...)` tránh lệch
  ngày.
- `restore_task()` kiểm tra conflict partial unique index trước khi khôi phục.
- `get_agenda()` deduplicate `in_progress` khỏi các nhóm khác.
- Domain errors → HTTP mapping rõ ràng (`DomainError → 400/404/409/422`).
- Prometheus metrics với route template label (tránh UUID cardinality
  explosion).
- Health endpoint tách live/ready, ready kiểm tra cả Postgres và Redis đồng
  thời (`asyncio.gather`).

Frontend — TypeScript strict, không `any`:

- Types sinh từ OpenAPI (`openapi-typescript`), committed vào git, có helper
  `WithRequired*` cho optional → required.
- `globalThis` store tránh Next.js dual module graph issue.
- Copy button có fallback cho non-secure context (truy cập qua LAN IP).
- `note-danger.ts` heuristic 15 danger rules + 5 secret rules — `is_dangerous`
  flag user-set, không phải máy quyết.
- Timezone format tường minh `"Asia/Ho_Chi_Minh"` tránh hydration mismatch.
- `noUncheckedIndexedAccess: true` — cấu hình TypeScript rất strict.

Enum xử lý thông minh: `enum_column()` helper → `native_enum=False` (VARCHAR +
CHECK) để thêm giá trị không cần `ALTER TYPE`, tránh Alembic sinh diff nhiễu.

### C. Tài liệu — điểm mạnh nhất

Hệ thống tài liệu có tầng, tiết kiệm token, tập trung cạm bẫy thật:

| Tầng | Nạp khi nào | File |
|---|---|---|
| Luôn nạp | Mọi session | `project.md`, `ops.md` |
| Theo file đang sửa | Tự động (`fileMatch`) | `backend-conventions.md` (9 quy tắc), `web-conventions.md` (12 quy tắc), `comment-style.md` |
| Theo việc đang làm | Skill tự phát hiện | `git-commit` (Conventional Commits), `add-entity` (15 bước checklist) |
| Gọi tay | `#status` | `status.md` (trạng thái bàn giao) |

Thêm 3 file docs cho 3 đối tượng:

- Người dùng: `docs/huong-dan-su-dung.md` (338 dòng)
- Developer: `docs/git-workflow.md` (281 dòng)
- Vận hành: `docs/deploy-runbook.md` (441 dòng)

Đặc biệt, skill `add-entity` là checklist 15 bước xuyên suốt backend →
frontend. Bỏ 1 bước sẽ lỗi ở chế độ `DATA_SOURCE` bạn không test.

### D. Ops & Monitoring chuyên nghiệp

- Smoke test 531 dòng gọi HTTP thật: healthcheck, metrics, CRUD lifecycle,
  tags, sorting, agenda, stats, trash, import/export, constraints. Tự dọn dữ
  liệu.
- 9 alert rules trong 4 groups: availability (probe/API down, cert hết hạn),
  api-health (5xx rate, p95 latency), resources (RAM, disk), postgres (down,
  connections).
- Makefile 316 dòng, 40+ targets: bootstrap, lifecycle, testing, profiles, LAN,
  production, git flow.
- Bootstrap 216 dòng tự động 8 bước: env check → CRLF fix → .env gen → build →
  postgres/redis up → migration → api/web up → smoke.
- Release script 327 dòng: `main → uat → prod` fast-forward only, semver
  validation, rollback instructions.

### E. Bảo mật có suy nghĩ

- Tất cả port bind `127.0.0.1` (không expose ra LAN mặc định).
- `secrets.compare_digest()` cho API key (timing-safe).
- Note content tuyệt đối không eval/exec — banner an toàn rõ ràng.
- `raw_payload` documented là untrusted data.
- `.env` chmod 600, PostgreSQL dùng `scram-sha-256`.
- Trang `/system` không render secret thật, dùng `<SensitiveToggle>`.
- Security headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`.

---

## 3. Điểm yếu & rủi ro

### Nghiêm trọng (block chạy trên macOS)

| # | Vấn đề | Files ảnh hưởng | Giải pháp |
|---|---|---|---|
| 1 | `sed -i` không tương thích macOS | Makefile (4 chỗ), `bootstrap.sh`, `gen-env.sh` | Đổi thành `sed -i '' 's/.../'` hoặc cài GNU sed |
| 2 | `changelog.sh` dùng `declare -A` (bash 4+) | `scripts/changelog.sh` | macOS ship bash 3.2. Cần `brew install bash` |

### Trung bình (nên sửa sớm)

| # | Vấn đề | Chi tiết |
|---|---|---|
| 3 | Không có unit test | Chỉ có smoke test (integration 531 dòng). Refactor lớn thiếu tự tin. |
| 4 | Rate limiting khai báo nhưng chưa implement | Config có `RATE_LIMIT_ENABLED` nhưng chưa có middleware. Redis đã sẵn. |
| 5 | `_priority_rank()` dùng case syntax cũ | Dict-style `case()` deprecated trong SQLAlchemy 2.0. Sẽ emit warning. |
| 6 | `TimestampMixin.onupdate` là Python-side | `onupdate=func.now()` là ORM event, không phải DB trigger. Raw SQL update sẽ không cập nhật `updated_at`. |
| 7 | Không có error toast ở frontend | Server Action lỗi không có UI feedback cho user. |

### Nhẹ (khi có thời gian)

| # | Vấn đề | Chi tiết |
|---|---|---|
| 8 | `node-exporter` + `cadvisor` không chạy đúng trên Docker Desktop | Đã document. Không ảnh hưởng app. |
| 9 | Timezone hardcode `"Asia/Ho_Chi_Minh"` ở frontend | OK single-user, cần env var nếu mở team. |
| 10 | Architecture diagrams toạ độ tay (530+702 dòng) | Khó maintain khi mở rộng. |
| 11 | Không có Suspense/loading state | OK cho personal tool. |
| 12 | `\r\n` line ending trong `note.py` | Tàn dư từ Windows. `make fix-eol` đã có sẵn. |
| 13 | Bootstrap error messages nói `apt install` / `systemctl` | Ubuntu-specific, gây confuse trên macOS. |
| 14 | `lan-up` hướng dẫn dùng `ip addr` | macOS cần `ifconfig` hoặc `ipconfig getifaddr en0`. |

---

## 4. Đánh giá theo tiêu chí

| Tiêu chí | Điểm | Ghi chú |
|---|---|---|
| Kiến trúc | 9/10 | Multi-source từ đầu, tách biệt rõ, soft delete + partial index thoughtful |
| Backend code | 9/10 | Async xuyên suốt, service layer 611 dòng có cấu trúc, domain error mapping, timezone đúng |
| Frontend code | 8/10 | TypeScript strict, Server Component đúng cách, types từ OpenAPI. Trừ: thiếu error UI, loading state |
| Tài liệu | 9.5/10 | Xuất sắc. Phân tầng token-efficient, tập trung cạm bẫy thật, 3 đối tượng rõ ràng |
| Ops / Infra | 9/10 | 40+ Makefile targets, bootstrap tự động 8 bước, monitoring 9 alerts, release flow |
| Bảo mật | 8.5/10 | API key đúng cách, timing-safe compare, port binding 127.0.0.1, note không eval. Thiếu rate limit + RBAC |
| Test coverage | 6.5/10 | Smoke test 531 dòng rất tốt nhưng thiếu unit test hoàn toàn |
| Developer Experience | 9/10 | Makefile, hot reload, 3 data modes, hooks, skills, bootstrap — onboard cực nhanh |
| Khả năng mở rộng | 8.5/10 | Roadmap 5 phase, kiến trúc sẵn sàng. Enum sources đã có sẵn Jira/Calendar/GitHub/GitLab |

**Tổng: 8.5/10** — Chất lượng vượt trội so với đại đa số dự án cá nhân. Đặc
biệt hệ thống tài liệu `.kiro/` phân tầng và smoke test 531 dòng — hai thứ mà
nhiều dự án công ty cũng không có.

---

## 5. So sánh với status.md

Một số thông tin trong `.kiro/steering/status.md` đã outdated:

| Nội dung status.md | Thực tế (02-10-2026) |
|---|---|
| `migrations/versions/` trống | Đã có `22721dfd9b56_initial_schema.py` (10.303 bytes) |
| Chưa từng chạy trên Ubuntu | Vẫn đúng — chưa runtime verify |
| 2 bug đã sửa chưa verify | Vẫn đúng — cần smoke test xác nhận |

---

## 6. Kế hoạch hành động

### Giai đoạn 1 — Chạy được trên macOS

| Bước | Việc | Ước tính |
|---|---|---|
| 1 | Sửa `sed -i` → `sed -i ''` trong 6 file (Makefile, bootstrap.sh, gen-env.sh) | 10 phút |
| 2 | Cài bash 5: `brew install bash` (cho changelog.sh) | 2 phút |
| 3 | Sửa error messages Ubuntu → macOS-compatible | 5 phút |
| 4 | `make bootstrap` — build, apply migration, smoke test | 5–15 phút |
| 5 | Sửa bug nếu smoke test fail | Tuỳ |

### Giai đoạn 2 — Ổn định

| Bước | Việc |
|---|---|
| 6 | Sửa `_priority_rank()` deprecated case syntax |
| 7 | Thêm error notification (toast) ở frontend |
| 8 | Implement rate limiting middleware |
| 9 | `make mon-up` — xác nhận monitoring (trừ node-exporter) |
| 10 | Cập nhật `status.md` cho đúng trạng thái hiện tại |

### Giai đoạn 3 — Phase 2

| Bước | Việc |
|---|---|
| 11 | Chốt Jira Cloud hay Data Center |
| 12 | MCP server đầu tiên |
| 13 | Telegram bot (long polling) |
