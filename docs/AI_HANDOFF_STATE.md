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

*--- Bản cập nhật cuối cùng: [2026-10-08] ---*
