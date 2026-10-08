# Master System Blueprint (Bản đồ Toàn cảnh Hệ thống)

> **🎯 MỤC ĐÍCH (Dành cho AI Agent):** Đọc file này ĐẦU TIÊN để nắm bắt toàn bộ kiến trúc, chức năng, và logic cốt lõi của dự án chỉ trong 1 lần đọc. File này được thiết kế cô đọng (token-optimized) để tiết kiệm Credit (Tokens) thay vì phải đọc rải rác 20 file tài liệu khác.

---

## 1. Tổng quan Kiến trúc (Monorepo)
Dự án là một Monorepo chia làm 2 ứng dụng độc lập:
- **`apps/web` (Frontend):** Next.js 15, React 19 (App Router), Tailwind v4. Sử dụng Server Actions.
- **`apps/core` (Backend API):** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic.
- **`infra` (Hạ tầng):** Docker Compose với 3 profile (Core, LiteLLM Gateway, Monitoring).

## 2. Các Chức năng Hệ thống (System Features)
### A. Quản lý Task (Đã hoàn thiện)
- **Cấu trúc Dữ liệu:** Hỗ trợ đa nguồn `(source, external_id)` để tích hợp bên thứ 3 (Jira, Calendar). Có Soft-delete (`deleted_at`).
- **Giao diện Web:** 
  - Trang Hôm nay (Agenda) & Trang Tất cả Task.
  - Hỗ trợ lọc (Filter) đa chiều, lưu state trên URL Params (`?assignee=...&time=...`).
  - Thao tác nhanh: Complete, Ghi nhận thời gian, Xếp vào hôm nay, Đồng bộ Jira.
- **Team Page:** Hiển thị danh sách thành viên. Bắt buộc hiển thị cả người có `0` task thông qua logic khởi tạo từ danh sách User gốc.

### B. Tích hợp Jira (Jira Quick Sync)
- **Cơ chế:** Polling định kỳ hoặc User bấm nút. Gọi API qua Jira Cloud (`/rest/api/3/search/jql`).
- **Idempotent:** Không tạo trùng task nhờ kiểm tra cặp khoá `(source='jira', external_id)`.
- **UI Feedback:** Cập nhật ngầm bằng `router.refresh()` thay vì tải lại toàn trang (F5).

### C. Giao diện & Trải nghiệm (UI/UX)
- Áp dụng triết lý thiết kế **Glassmorphism** toàn diện (Nền mờ `backdrop-blur`, viền mờ `border-white/20`, gradient tinh tế).
- Mọi thao tác form đều có Validation (bắt lỗi) và hiển thị thông báo Toast/Alert thân thiện.

---

## 3. Quản lý Lưu trữ (Data Storage)
Hệ thống linh hoạt chuyển đổi qua biến môi trường `DATA_SOURCE`:
1. **`file` (Local JSON - Đang dùng cho Phase 1):** Dữ liệu lưu tại `data/builder-data.json`. Sử dụng `SCHEMA_VERSION` (hiện là v4) để tự động Migrate dữ liệu cũ.
2. **`api` (Postgres - Dành cho Phase 2):** Sử dụng `pgvector` phục vụ RAG (tìm kiếm AI cho Notes). Bắt buộc dùng `scram-sha-256` để bảo mật.
3. **`memory`:** Dùng chạy Smoke Test CI/CD.

---

## 4. Hệ thống Quy tắc Lập trình (Agent Constraints)
Bất kỳ AI nào code trong dự án này BẮT BUỘC tuân thủ:
1. **Frontend:** Không lọt API Key xuống Browser. Luôn dùng `globalThis` cho kết nối Database (tránh sập kết nối khi HMR - Hot Reload).
2. **Backend:** Trả về JSON chuẩn hoá. Bắt buộc xử lý ngoại lệ an toàn, không Crash.
3. **Quy trình Hoàn thiện (Rule 3.10):** Code -> Viết Docs -> Chạy kiểm thử (Skill `qc-uat`) -> Báo cáo.
4. **Git Flow (Rule 3.11):** Không tự ý Push code nếu chưa xin phép. Push phải có `CHANGELOG.md`.
5. **Ghi vết phiên AI:** do hook Claude Code làm tự động (mặc định tắt), xem `docs/CLAUDE_TRACE_HOOKS.md`. AI log viết tay đã gỡ.

---
*Nếu bạn là AI, sau khi đọc xong file này, bạn đã sở hữu 95% tri thức của hệ thống. Hãy bắt tay vào giải quyết yêu cầu của User ngay lập tức!*
