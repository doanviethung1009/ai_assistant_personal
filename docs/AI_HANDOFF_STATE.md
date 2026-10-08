# Trạng thái Bàn giao Hệ thống (AI Handoff State)

> **LƯU Ý DÀNH CHO AI AGENT:** 
> Đọc kỹ file này vào đầu mỗi phiên làm việc (Session) để nắm bắt bối cảnh hiện tại. Sau đó, **BẮT BUỘC đọc file `docs/project-review.md` (Master Blueprint)** để lấy toàn bộ kiến trúc và chức năng hệ thống chỉ trong 1 lần đọc (Giúp tiết kiệm Credit/Token thay vì đọc 20 file rải rác).

## 1. Bối cảnh & Kiến trúc Hiện tại (Phase 1)
- **Frontend (Web):** Next.js App Router, TailwindCSS. Đã áp dụng toàn diện thiết kế **Glassmorphism** (trong suốt, bóng đổ, gradient hiện đại).
- **Backend/Data:** Hiện đang sử dụng **Local JSON** (`data/builder-data.json`) để lưu trữ dữ liệu. Kiến trúc này đáp ứng nhu cầu phát triển cực nhanh cho Phase 1 và sử dụng cá nhân hoàn hảo qua lệnh `npm run dev`.
- **Hệ thống DevOps:** Đã chuẩn bị sẵn sàng cấu hình Docker cực chuẩn (Rootless, pgvector, Nextjs Standalone) nằm trong `docker-compose.yml`, dọn đường cho Phase 2.

## 2. Tính năng đã hoàn thiện & Xác nhận (QC-Passed)
- **Đồng bộ Jira (Jira Sync):** Giao diện đã mượt mà, sử dụng `router.refresh()` ngầm, giữ State ổn định, có log thời gian đồng bộ cuối cùng.
- **Quản trị Team:** Bộ lọc đa chiều trên URL Params (time, status), khắc phục thành công lỗi mất thành viên khi số lượng task = 0 (tự động khởi tạo count = 0 cho mọi assignees).
- **Trang Tài liệu (Docs):** Hệ thống Markdown tự động render lên Web. Đã đăng ký đầy đủ tài liệu về Kiến trúc (Target, Docker, Deploy) và Kỹ năng AI (QC UAT).

## 3. Hệ thống Rules & Trí tuệ AI (Agentic Protocols)
- Dự án áp dụng bộ luật vô cùng khắt khe tại `AGENTS.md` (từ 3.1 đến 3.11).
- **Luật nổi bật:**
  - `Rule 3.10`: Vòng đời phát triển phải qua 3 bước: Code -> Docs -> QC.
  - `Rule 3.11`: CẤM tự ý Push Git nếu chưa được User Confirm. Khi Push phải có Changelog.
  - `Rule 3.9`: Mọi thay đổi về hạ tầng (Docker/CI/CD) phải được viết comment trực tiếp và có tài liệu giải thích.

## 4. Định hướng Tiếp theo (To-do / Phase 2)
1. **Chuyển đổi Backend (Phase 2):** Khi User yêu cầu mở rộng, sẽ chuyển dịch từ Local JSON sang mô hình Backend độc lập (FastAPI + Postgres) theo đúng định hướng tại `docs/TARGET_ARCHITECTURE.md`.
2. **Triển khai AI/Vault:** Tích hợp `pgvector` cho tìm kiếm ngữ nghĩa (Notes) và Zero-Knowledge Encryption cho Vault.
3. **Mở rộng RBAC:** Tích hợp logic phân quyền phức tạp theo chuẩn trong `.agents/skills/rbac-implementation/SKILL.md`.

## 5. Cập nhật 08-10-2026: multi-agent, CI, backend

- **Multi-agent (Claude Code):** 6 subagent trong `.claude/agents/` (architect, backend-dev, frontend-dev, db-reviewer, code-reviewer, security-auditor), hook an toàn, quyền allow/ask/deny. Đọc `docs/MULTI_AGENT_SYSTEM.md`; ví dụ chạy thật ở `docs/MULTI_AGENT_TRIAL.md`.
- **Backend đã sửa:** router `ai-logs` từng import module không tồn tại nên API không khởi động; thêm migration `ai_logs`, `tasks.assignee`, `notes.archived_at`. `TaskRead` nay trả `assignee`. `GET /tasks?assignee=` lọc thật.
- **Test và CI:** `apps/core/tests/` (43 test, cần Postgres cho phần lớn), `make test` chạy trên DB riêng `<POSTGRES_DB>_test`, CI ở `.github/workflows/ci.yml`. Xem `docs/CI_AND_TESTING.md`.
- **Tính năng Lưu trữ note** (nhánh thử `trial/multi-agent-note-archive`): chỉ hoạt động ở `DATA_SOURCE=api`; chế độ file JSON (mặc định của web) ẩn tính năng và trả 501. Spec: `docs/specs/note-archive.md`.
- **`lib/generated/openapi.d.ts` đã được sinh lại từ `app.openapi()`.** Trước đó nó bị vá tay (thêm `assignee` vào Note và Project) nên che lỗi; đừng sửa tay file này, dùng `make gen-types`.
- **Bảo mật web:** mọi route trong `lib/api.ts` có `id` đều đi qua `pathId()` (chỉ nhận UUID) để chặn path injection qua Server Action; route mới có `id` phải dùng helper này.
- **Chưa làm / cần chú ý:** `npm audit` còn 4 lỗ hổng high; web chưa có đăng nhập; chưa chạy `make smoke` và chưa xem giao diện Lưu trữ trên trình duyệt (máy dev không có Docker).

## 6. Chuyển dữ liệu từ file JSON sang Postgres (đang làm, 4 pha)

- **Spec CHỐT:** `docs/specs/import-json-to-postgres.md` (User duyệt B1-B4, quyết định replace có rào chắn, Vault KHÔNG vào Postgres). Hướng dẫn dùng và hoàn tác: `docs/DATA_MIGRATION_TO_POSTGRES.md`.
- **B1 đã code (nhánh `feat/import-b1`, chưa merge):** `POST /api/v1/import/datafile` và `/import/ai-logs`; migration `e5f1a3b7c9d2` (bảng `import_runs`, `import_audit`); panel nhập ở tab Nhập của trang Dữ liệu khi `DATA_SOURCE=api`. Rào chắn: `dry_run` mặc định, `expect_replaced`, `expect_sha256`, mật khẩu `IMPORT_COMMIT_SECRET` (header `X-Import-Secret`), advisory lock, khoá dòng, all-or-nothing, audit `before`.
- **Việc cần làm khi bắt đầu dùng:** `.env` hiện có phải tự thêm `IMPORT_COMMIT_SECRET` (`make env` chỉ sinh khi tạo `.env` mới); thiếu thì core từ chối nhập thật.
- **B2 (cài đặt người dùng, sync_urls) và B4 (Jira sync ở backend) chưa làm (B3 lịch sử Chrome đã bị gỡ, xem mục 9).** Đến lúc đó chế độ `api` vẫn chưa có Jira sync, nhập Excel, lọc task cá nhân/team, nên chưa bỏ chế độ file.
- **Vault không nằm trong Postgres:** `pg_dump` không chứa nó; sao lưu riêng bằng `/api/export?entity=vault`.
- **Rủi ro đã ghi nhận:** web không có đăng nhập; file cũ có thể ghi đè trạng thái mới hơn (đã có cờ "File cũ hơn" và xác nhận 2 lớp); `import_audit.before` giữ bản sao đầy đủ và chưa có chính sách xoá.
- **`data/builder-data.json` là dữ liệu thật của User:** test chỉ mở chế độ đọc (kiểm sha256 không đổi); không bao giờ ghi hay chép vào repo.

## 7. Tách task công việc và cá nhân (`scope`)

- **Spec CHỐT:** `docs/specs/task-scope.md` (User duyệt S1-S15). Mỗi task có `scope` = `work` | `personal`; mặc định theo nguồn (`jira`/`github`/`gitlab` là work). "Việc của tôi" là bộ lọc `view=mine` (cá nhân + công việc giao cho tên trong `owner` + công việc tự tạo không assignee/không mã Jira), KHÔNG lưu thành cột. Định nghĩa dùng chung ở `apps/web/lib/task-scope.ts` (module thuần) và `_view_clause` ở backend; hai bên phải giữ tương đương.
- **Rào chắn:** Jira sync, nhập Excel/URL, nhập JSON và (sau này) `upsert-batch` B4 KHÔNG ghi đè task `personal` (đếm `skipped_personal`); nhập JSON có `include_personal` tuỳ chọn. Đổi một task Jira sang personal = tách khỏi đồng bộ.
- **File JSON lên phiên bản 5** (có migrate, kể cả khi restore); B2 sẽ dùng 6. Migration `f6a2b4c8d1e3` (`tasks.scope`, CHECK `ck_tasks_scope_valid`, down_revision `e5f1a3b7c9d2`): chỉ merge SAU PR nhập B1 (#12).
- **Lần đầu web ở chế độ file nạp dữ liệu thật sau khi merge, nó sẽ ghi lại thành phiên bản 5.** Sao lưu `data/` trước (nhật ký `.bak` tự có, nhưng hãy chép thêm).
- **Thứ tự pha mới:** B1 → S (xong code) → B2 → B4, B3 song song.
- **Lỗi có sẵn đã sửa trong epic:** `/team` ở chế độ api không còn gọi `limit=10000` (backend cho tối đa 200); `listTasks` ở chế độ api truyền `view`/`owner`/`assignee`; vùng nguy hiểm ở chế độ api không còn giả vờ xoá (hiện thông báo); `restoreFromJsonAction` chạy migrate.
- **Chưa làm / ghi nhận:** `file-upload-manager`, `url-sync-manager` chưa hiện `skipped_personal` (không thuộc Ownership frontend của epic); `/team` vẫn tải nhiều trang rồi lọc client-side (phân trang server-side là epic riêng); `/tasks` ở chế độ api nhận `size` tới 1000 còn backend tối đa 200 (lỗi có sẵn).

## 8. Cài đặt người dùng và URL đồng bộ (pha B2, đã merge vào `main`)

- **Đã code:** bảng `app_settings` (key khai báo cứng, migration `a7b3c5d9e2f4`, down_revision `f6a2b4c8d1e3`), `GET/PUT /api/v1/settings/current-users` và `/sync-urls`, `GET /api/v1/tasks/assignees` (chỉ `scope=work`); nhập `meta.current_users` và `sync_urls` từ file (thực thể `setting`). File JSON **phiên bản 6** (lưu `sync_urls`, lỗi cũ: `snapshot()` bỏ sót). Web ở chế độ api: `getCurrentUsersApi`/`getAssigneesApi`/`getSyncUrlsApi` gọi core thật, `CurrentUserManager` và `UrlSyncManager` dùng được.
- **Bảo mật (chống SSRF):** URL đồng bộ chỉ `https` + allowlist host (Google Docs/Sheets/Drive, SharePoint, OneDrive; thêm bằng `SYNC_URL_EXTRA_HOSTS`, đặt giống nhau cho api và web). Hai bản luật phải GIỮ TƯƠNG ĐƯƠNG: `apps/core/app/core/url_allowlist.py` và `apps/web/lib/url-allowlist.ts`. `syncFromUrlAction` kiểm `IS_LOCAL` trước, fetch `redirect: manual`, kiểm lại allowlist mỗi bước (tối đa 5).
- **Thay đổi hành vi chế độ file:** trước đây lưu URL đồng bộ bất kỳ; nay bị từ chối nếu ngoài allowlist.
- **Đã review và sửa (vòng 1):** Drive chuyển hướng sang `drive.usercontent.google.com` (đã thêm); Kelvin `K` lọt Python (đã chặn bằng `re.ASCII`); `SYNC_URL_EXTRA_HOSTS` từ chối host không dấu chấm và hậu tố dùng chung; tải file theo stream có trần 20 MB; thêm/xoá URL không bị khoá bởi URL cũ; PUT settings dùng chung advisory lock với nhập. Parity TS/Python đối chiếu 225 URL + 33 cấu hình, 0 lệch.
- **Rủi ro còn lại:** `*.sharepoint.com` và `*.googleusercontent.com` nhận mọi tenant (nội dung do bên khác kiểm soát được parse và nhập); chưa chặn IP nội bộ sau khi phân giải DNS (allowlist theo tên miền); `xlsx` 0.18.5 có CVE (việc riêng đã tách); OneDrive cá nhân chưa kiểm được; `jira-actions.ts` fetch `baseUrl` tuỳ ý kèm `Authorization` (SSRF có sẵn, để B4).
- **Merge:** sau PR task-scope (#13) vì migration nối tiếp. `.env` hiện có không có `SYNC_URL_EXTRA_HOSTS` (tuỳ chọn); Jira on-prem cần thêm host vào biến này.
- **Chưa làm:** pha B4 (Jira sync ở backend; nút "Cào ngay" ở chế độ api khoá cho tới lúc đó). Chưa chặn IP nội bộ sau khi phân giải DNS (allowlist theo tên miền; ghi nhận).

## 9. Lịch sử Chrome: đã GỠ HẲN (nhánh `chore/remove-browser-history`)

- **Quyết định (User xác nhận 08-10-2026):** không cần tính năng lịch sử duyệt web nữa, ở cả Postgres lẫn file JSON. Pha B3 từng làm xong rồi bị gỡ.
- **Đã gỡ:** backend (`api/v1/browser_history.py`, model, schema, service, route `POST /import/browser-history`, test, mục TRUNCATE trong conftest); migration MỚI `d7e2a9c4b1f6` xoá bảng `browser_history` (down_revision `c9d1e3f5a7b2`; downgrade tạo lại bảng đúng như `b8c4d6e0f3a5`, đã so `pg_dump -s` giống hệt). Web: trang `/history`, `lib/chrome-history.ts`, `actions-chrome.ts`, `chrome-history-manager.tsx`, mục menu, loại file `chrome-history.json` ở panel Nhập, hàm trong `lib/api.ts`, alias trong `lib/types.ts`, tuỳ chọn xoá/backup Chrome ở chế độ file (`wipe-data-manager`, `store/engine.ts`). `openapi.d.ts` sinh lại.
- **Giữ nguyên:** migration cũ `b8c4d6e0f3a5` (không sửa lịch sử Alembic); `guard_import_secret`, `ImportSecretHeader` (B4a/B4b dùng); phần che `input` của 422 trong `main.py` (chỉ bỏ hai tiền tố browser-history); file `data/chrome-history.json` của User (không xoá; trước đây `wipe_all_data` có thể xoá nó, nay thì không).
- **Backup cũ:** vòng dọn `data/backups/` xoá mọi `*.json`, nên lần xoá dữ liệu đầu tiên sau thay đổi này cũng xoá các `chrome-history-backup-*.json` cũ (file gốc `data/chrome-history.json` vẫn giữ).
- **Merge:** đã merge sau B4b (migration `d7e2a9c4b1f6` là head, B4b không thêm migration).
- **Bảng `browser_history` ở DB đang chạy sẽ bị xoá khi `make migrate`;** muốn giữ dữ liệu thì `pg_dump -t browser_history` trước.

## 10. Jira ở backend, phần B4a: kết nối mã hoá và upsert-batch (đã merge vào `main`)

- **Đã code:** bảng `integration_connections` (migration `c9d1e3f5a7b2`, nối sau `b8c4d6e0f3a5`), `/api/v1/integrations` (token chỉ ghi, mã hoá Fernet, gắn với `connection_id` + `base_url` nên chép ciphertext sang kết nối khác sẽ không giải mã được), `POST /tasks/upsert-batch` (cần `X-Import-Secret`, chỉ ghi `scope=work`, tags gộp, description chỉ điền khi rỗng, lọc `raw_payload`), `POST /import/verify-secret`. Thêm gói `cryptography` (uv.lock chỉ thêm 3 gói). Web: `jira-connections-manager` (quản lý kết nối, chuyển cấu hình từ localStorage một lần), Excel/URL sync ở chế độ api đẩy lên upsert-batch, `lib/excel-upsert.ts`.
- **Biến môi trường mới:** `INTEGRATION_SECRET_KEY` (khoá Fernet; `make env` tự sinh, **.env có từ trước phải tự thêm**; mất khoá = nhập lại mọi token), `INTEGRATION_SECRET_KEY_OLD` (tuỳ chọn, khi xoay khoá).
- **Thay đổi hành vi:** route `GET /api/sync` đã **xoá** (ghi dữ liệu không xác thực, có thể bị CSRF qua thẻ img); `JiraQuickSync` ẩn ở chế độ api; `XLSX.read` giới hạn 50 000 dòng cả ở chế độ file; dòng Excel thiếu Issue Key bị bỏ ở chế độ api; ô Excel trống gửi `null` (xoá hạn, người giao, project) cho khớp chế độ file; priority không còn bị đặt lại.
- **Lệch spec cần nhớ:** actor event là `integration:<source>` (B4b nên đổi thành tên kết nối); `GET /integrations` trả `Page`; `TaskSource` không có `url_sync`/`excel` nên web gửi `source=jira` cố định ở server; tạo kết nối không có token vẫn được khi thiếu khoá (chỉ token mới cần khoá).
- **Rủi ro còn lại:** `base_url` mới chỉ chặn theo tên host literal, **chưa phân giải DNS** (`127.0.0.1.nip.io`, DNS rebinding): B4b phải phân giải, chặn IP private, ghim IP, tắt redirect, không gửi `Authorization` sang host khác; `syncJiraAction` ở chế độ file vẫn gửi `Authorization` tới `baseUrl` tuỳ ý (SSRF có sẵn, vá ở B4b); tạo/xoá kết nối chưa đòi mật khẩu (web không có đăng nhập); audit kết nối chỉ là log có cấu trúc, chưa có bảng; `external_url` hardcode `onemount.atlassian.net`; chưa chạy UAT, `make smoke` (không có Docker).
- **Chưa làm (B4b):** `POST /integrations/{id}/sync` (connector Python trong core, mặc định chặn IP private, mở bằng biến môi trường), JQL mặc định dùng `current_users`, bật nút "Cào ngay" ở chế độ api.

## 11. Chạy sync Jira ở backend, phần B4b (nhánh `feat/jira-sync-b4b`, chưa merge)

- **Đã code:** `POST /api/v1/integrations/{id}/sync` (cần `X-Import-Secret`). Connector Python trong core: `services/jira_client.py` (phân trang, JQL, giới hạn), `jira_mapping.py` (ánh xạ issue sang task, khớp `syncJiraAction` chế độ file), `ssrf_guard.py` (phân giải DNS, chặn IP riêng, ghim IP), `integration_sync_service.py` (khoá advisory theo kết nối, ghi từng lô ngắn, không giữ transaction lúc gọi Jira). Web: nút "Cào ngay" ở chế độ api (mật khẩu, "Từ ngày", kết quả chi tiết).
- **Chỉ Jira Cloud** (`*.atlassian.net`, User chốt). Không có cờ cho phép IP riêng/Jira on-prem (đã bỏ có chủ đích). Mọi dải riêng, loopback, link-local, metadata cloud luôn bị chặn.
- **Vá SSRF có sẵn:** `syncJiraAction` (chế độ file) trước đây gửi `Authorization` tới `baseUrl` tuỳ ý và trả body lỗi của Jira. Nay chỉ nhận `https://<nhãn>.atlassian.net`, không theo redirect, không trả/log body Jira, có trần tổng 100 MB, hạn chót 5 phút, chống chạy song song, kiểm `issue.key`, escape JQL. **Thay đổi hành vi:** chế độ file không còn nhận host khác.
- **Parity chế độ file:** `priority`, `due_at`, `assignee`, project chỉ ghi khi tạo task; task cũ giữ giá trị User sửa tay.
- **Thêm gói:** `httpcore` khai báo tường minh (chốt SSRF dùng trực tiếp).
- **Rủi ro còn lại:** chưa UAT với Jira Cloud thật, chưa `make smoke` (không có Docker); chế độ file không đòi mật khẩu cho Jira sync (chế độ một máy, web chưa có đăng nhập) và token Jira vẫn ở `localStorage` ở chế độ file; cờ chống chạy song song của chế độ file chỉ có tác dụng trong một process; ánh xạ priority Jira chưa dùng khi cập nhật; `external_url` ở `excel-upsert.ts` còn hardcode `onemount.atlassian.net`; `_ORDER_BY_RE` cắt cả chữ "order by" nằm trong chuỗi JQL; còn vài `any` cũ trong `syncJiraAction`; JiraQuickSync vẫn ẩn ở chế độ api.
- **Phát hiện hạ tầng test:** assert "token không có trong caplog" ở các test cũ (B3, B4a) có thể vô nghĩa vì fixture migrate tắt logger của app; đã tách thành việc riêng (chip chore/fix-caplog-tests). `test_jira_sync_api.py` đã bật lại logger.
- **Chuỗi B1-B4 đã xong về code.** Việc còn lại ngoài B4b: gỡ tính năng lịch sử duyệt web (User không cần nữa, session riêng), nâng `xlsx` (2 CVE), UAT ở máy có Docker.

## 12. Hook ghi vết Claude Code (nhánh `feat/claude-trace-hooks`, giai đoạn 1, chưa merge)

- Hook `Stop`/`SubagentStop`/`SessionEnd` (`.claude/hooks/trace-hook.py` + `trace_redact.py`) ghi vết ngoài repo (`~/.claude/trace/ai_assistant_personal/`), lọc secret trước khi ghi. Giai đoạn 1 chỉ THÊM (nay đã sang giai đoạn 2, xem mục 13); AI log viết tay, bảng `ai_logs`, `/ai-logs` giữ nguyên để so sánh. **Mặc định TẮT**, bật bằng `CLAUDE_TRACE_ENABLED=1` trong `.claude/settings.local.json` (gitignore). Chi tiết: `docs/CLAUDE_TRACE_HOOKS.md`.
- **User chốt (2026-10-08):** lưu tóm tắt từng lượt + transcript đã lọc; dữ liệu Jira công ty **chưa được dùng để train** (chưa rõ chính sách). Giai đoạn 2 (gỡ AI log viết tay) đã làm ở mục 13.

## 13. Gỡ AI log viết tay + xoay vòng trace (nhánh `chore/remove-handwritten-ai-log`, chưa merge)

- **Đã gỡ (User duyệt 2026-10-08):** rule `ai-logger.md`, mục 3.4 AGENTS.md (nay chỉ là con trỏ tới hook ghi vết), `scripts/add-ai-log.js`, `docs/ai_logs.md`, bảng `ai_logs` (migration `f3a8c1d5e7b9`, `down_revision d7e2a9c4b1f6`, downgrade tạo bảng RỖNG), API `/ai-logs` và `/import/ai-logs`, trang `/ai-logs`, nhánh import/export JSON nhật ký AI. Spec: `docs/specs/remove-handwritten-ai-log.md`.
- **Bản sao log cũ** (72 mục + `ai_logs.md`) nằm NGOÀI repo: `~/.claude/trace/ai_assistant_personal/legacy-ai-logs/`. `data/ai-logs.json` của User để nguyên (gitignore), web thôi đọc.
- **Giữ có chủ ý:** `ImportKind.AI_LOGS`, `ImportEntity.AI_LOG` và CHECK cũ ở `import_runs`/`import_audit` (dòng sổ cái cũ còn giá trị đó).
- **`make migrate` trên DB thật sẽ XOÁ bảng `ai_logs` cùng dữ liệu** (hỏi User trước; xuất `\copy ai_logs ...` nếu muốn giữ).
- **Xoay vòng trace:** transcript trong `sessions/` cũ hơn `CLAUDE_TRACE_RETENTION_DAYS` (mặc định 90) bị xoá khi `SessionEnd`.
- **Đề xuất training:** `docs/LLM_TRAINING_DATA_PLAN.md` (chờ User chốt chính sách dữ liệu Jira).
- **Chưa kiểm:** `make smoke`, `make gen-types` (không có Docker; `openapi.d.ts` sửa tay), migrate trên DB dev thật.

*--- Bản cập nhật cuối cùng: [2026-10-08] ---*
