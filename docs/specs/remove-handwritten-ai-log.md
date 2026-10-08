# Spec: gỡ hệ AI log viết tay

> Quyết định của User (2026-10-08): gỡ HẾT (rule ghi tay, script, bảng `ai_logs`, API, trang `/ai-logs`, import/export).
> Thay thế: hook ghi vết (`docs/CLAUDE_TRACE_HOOKS.md`). Bản sao log cũ đã lưu ngoài repo:
> `~/.claude/trace/ai_assistant_personal/legacy-ai-logs/` (ai-logs.json 72 mục, ai_logs.md).

## Ownership (không chồng chéo, không ai chạm git: orchestrator commit)

| Ai | Được sửa |
|---|---|
| backend-dev | chỉ `apps/core/` |
| frontend-dev | chỉ `apps/web/` (trừ `apps/web/lib/docs.ts`: orchestrator) |
| orchestrator | `.agents/`, `AGENTS.md`, `CLAUDE.md`, `scripts/`, `docs/`, `apps/web/lib/docs.ts` |

## Backend (`apps/core`)

Xoá hẳn: `app/models/ai_log.py`, `app/schemas/ai_log.py`, `app/services/ai_log_service.py`,
`app/api/v1/ai_logs.py`, `tests/test_ai_logs_api.py`, `tests/fixtures/ai_logs_sample.json` (kiểm các test import
khác đang dùng fixture này và chỉnh cho khỏi vỡ).

Gỡ phần dùng chung (KHÔNG xoá file): `app/api/v1/router.py`, `app/models/__init__.py`,
`app/models/enums.py` (`AiLogCategory`, `ImportKind.AI_LOGS`, `ImportEntity.AI_LOG`: xem mục CHECK bên dưới),
`app/api/v1/imports.py` (endpoint `/import/ai-logs`), `app/schemas/imports.py` (`AiLogsEnvelope`, `ImportAiLog`, Literal),
`app/services/import_service.py` (`AI_LOG_FIELDS`, `map_ai_log_category`, `_parse_ai_log`, `import_ai_logs`, entry bảng),
test: `conftest.py:64` và `test_settings.py:635` (bỏ `ai_logs` khỏi TRUNCATE), `test_unit.py`, `test_import_unit.py`,
`test_import_api.py`, `test_import_service.py`, `scripts/test-backend.sh` (comment).

**Migration mới** (`down_revision = "d7e2a9c4b1f6"`, head hiện tại): drop index `ix_ai_logs_category` rồi bảng `ai_logs`,
và enum Postgres `ai_log_category` nếu có. `downgrade()` tạo lại bảng/index/enum y như `b7a41c9e3d20_add_ai_logs.py`
(bảng rỗng). KHÔNG sửa/xoá các migration cũ.

**CHECK ở `import_runs.kind` / `import_audit.entity`** còn cho phép `'ai_logs'`/`'ai_log'`: để NGUYÊN (ràng buộc dư thừa
vô hại; siết lại cần xử lý dòng audit cũ). Nên Python enum `ImportKind`/`ImportEntity` chỉ bỏ member nếu không còn dòng DB
nào đọc ra giá trị đó qua ORM; nếu không chắc thì giữ member và ghi chú vì sao. Ghi quyết định trong báo cáo.

Kiểm: `ruff`, `alembic heads` (một head), `alembic check`, upgrade → downgrade → upgrade trên Postgres tạm (xem
`docs/AI_HANDOFF_STATE.md` mục browser history: cổng 55433), toàn bộ pytest.

## Frontend (`apps/web`)

Xoá: `app/ai-logs/page.tsx`. Gỡ: `lib/nav.ts` (mục menu), `lib/api.ts` (`listAiLogs`, `createAiLog`, `importAiLogsFile`,
nhánh `postImport` ai-logs, import `reloadAiLogsFromDisk`), `app/actions.ts`, `app/api/export/route.ts`,
`components/data-export-grid.tsx`, `components/data-import.tsx`, `components/core-import-panel.tsx`,
`lib/store/engine.ts`, `lib/store/json-file.ts`, `lib/store/transfer.ts`, `lib/store/types.ts` (`AiLogsFile`),
`lib/types.ts` nếu có alias. Không có Docker để sinh lại: sửa tay `lib/generated/openapi.d.ts` bỏ đúng phần AI log
(paths `/ai-logs`, `/import/ai-logs`, schema `AiLog*`, `Page_AiLogRead_`, enum `ai_log`, operations tương ứng).
**Không đổi `SCHEMA_VERSION`** (ai_logs đã tách khỏi DataFile từ v4); file cũ `data/ai-logs.json` của User để nguyên, web chỉ thôi đọc.
Kiểm: `npx tsc --noEmit` (bỏ qua lỗi cũ ở `.next/types`), grep không còn `ai_log|AiLog|ai-logs` ngoài ghi chú.

## Orchestrator

Xoá `.agents/rules/ai-logger.md`, `scripts/add-ai-log.js`, `docs/ai_logs.md`; sửa `AGENTS.md` mục 3.4, `CLAUDE.md`,
`.agents/rules/web-conventions.md`, `apps/web/lib/docs.ts` (bỏ mục ai-logs, thêm `LLM_TRAINING_DATA_PLAN.md`),
`docs/*` có nhắc (xem grep), thêm `docs/LLM_TRAINING_DATA_PLAN.md` vào INDEX. `CHANGELOG.md` không sửa tay.

## Rủi ro / lưu ý khi áp dụng

- `make migrate` trên DB thật xoá bảng `ai_logs` cùng dữ liệu. Xuất trước nếu muốn giữ:
  `make psql` rồi `\copy ai_logs TO 'ai_logs_backup.csv' CSV HEADER` (chạy trong container, lấy file ra).
- Quy tắc cũ "ghi AI log cuối mỗi task" biến mất; hook ghi vết (mặc định TẮT) là cơ chế thay thế.
