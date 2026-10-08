# Cẩm nang Nhập môn cho AI Agent Mới (New Agent Onboarding)

Tài liệu này định nghĩa "Cách thức hoạt động chuẩn" (Standard Operating Procedure) dành cho bất kỳ AI Agent nào (Gemini, Claude, Cursor, v.v.) vừa được khởi tạo hoặc bắt đầu một phiên làm việc (session) mới trong dự án này.

> **Dành cho User:** Bạn có thể trỏ AI đọc file này khi chúng có dấu hiệu "ngáo" hoặc làm sai quy trình.
> **Dành cho AI:** Nếu bạn đang đọc dòng này, đây là những việc bạn **BẮT BUỘC** phải làm.

---

## 1. Cách thu thập thông tin (Context Retrieval)

Ngay khi bắt đầu một phiên chat, AI Agent KHÔNG ĐƯỢC đoán mò bối cảnh. Hãy thực hiện theo trình tự:

1. **Đọc Trạng thái Bàn giao (Handoff State):** 
   - Dùng tool đọc file `docs/AI_HANDOFF_STATE.md`. 
   - File này chứa "ảnh chụp" mới nhất về việc dự án đang ở Phase nào và tính năng nào vừa làm xong.
2. **Đọc Bản đồ Hệ thống (Master Blueprint):**
   - Đọc file `docs/project-review.md`. Đây là bước SIÊU QUAN TRỌNG. Thay vì đọc 20 file riêng lẻ, chỉ cần đọc file này để nắm toàn cảnh kiến trúc (DB, UI, Rules) và tiết kiệm Token.
3. **Đọc Cấu trúc Dự án (Project Structure):**
   - Đọc `docs/PROJECT_STRUCTURE.md` để biết file code nào nằm ở đâu (`apps/web` hay `apps/core`).
4. **Đọc Kiến trúc Mục tiêu (Target Architecture):**
   - Nếu User yêu cầu làm tính năng lớn liên quan đến Database, Task, Note, Vault, phải đọc `docs/TARGET_ARCHITECTURE.md` để thiết kế cho đúng hướng.

---

## 2. Hệ thống Luật bắt buộc tuân thủ (Mandatory Rules)

Toàn bộ luật tối cao nằm ở file gốc `AGENTS.md`. AI phải tuân thủ nghiêm ngặt 11 luật thép (Rule 3.1 đến 3.11). Dưới đây là các luật "tử huyệt" cấm vi phạm:

1. **Rule 3.10 (Vòng đời Tính năng):** Làm xong 1 tính năng phải đi qua 3 bước: **Viết Code -> Cập nhật Docs -> Chạy Skill QC (Nghiệm thu)**. Bỏ qua bước nào coi như AI thất bại.
2. **Mục 3.4 (Ghi vết):** không còn ghi AI log bằng tay; hook ghi vết tự động (mặc định tắt), xem `docs/CLAUDE_TRACE_HOOKS.md`.
3. **Rule 3.11 (Bảo vệ Git):** TUYỆT ĐỐI CẤM tự ý Push code lên Git nếu chưa hỏi và được User cho phép (Confirm).
4. **Rule 3.9 (Minh bạch Hạ tầng):** Khi đụng vào file hệ thống, Docker, Makefile, AI phải comment giải thích từng dòng trong code và viết `.md` để User dễ kiểm soát.

---

## 3. Cách sử dụng Kỹ năng (Skill Activation)

AI không nên code bằng "bản năng" (zero-shot) đối với các tác vụ phức tạp.

- **Vị trí Skill:** Tất cả các luồng làm việc chuẩn đã được đóng gói tại `.agents/skills/`.
- **Cách dùng:** Khi được giao việc (ví dụ: Commit Git, Thêm bảng DB, Phân quyền RBAC), AI phải chủ động vào thư mục skill tương ứng, đọc file `SKILL.md` và làm y hệt như một cái máy check-list (từng bước một).
- **Các Skill đang có sẵn (10):**
  - `add-entity`: Thêm luồng dữ liệu mới từ DB lên Frontend.
  - `db-migration`: Tạo và áp migration Alembic an toàn.
  - `git-commit`: Chuẩn hoá commit message và sinh Changelog.
  - `qc-uat`: Kịch bản nghiệm thu phát hiện lỗi UI/UX, Logic, Dữ liệu.
  - `pr-review`: Review nhánh/PR trước khi merge.
  - `security-audit`, `e2ee-vault`, `rbac-implementation`: Bảo mật, Vault E2EE, phân quyền.
  - `architecture-design`, `docker-deploy`: Thiết kế hệ thống, triển khai.

---

## 4. Nếu bạn là Claude Code: làm việc theo mô hình orchestrator

Việc nhỏ (1–2 file, một tầng) thì tự làm. Việc chạm từ hai tầng trở lên thì dùng subagent trong `.claude/agents/` (architect → backend-dev/frontend-dev → db-reviewer, code-reviewer, security-auditor). Chỉ session chính (orchestrator) được cập nhật `docs/AI_HANDOFF_STATE.md`, đăng ký `lib/docs.ts` và commit. Chi tiết: `docs/MULTI_AGENT_SYSTEM.md`.

---

## 5. Tóm tắt Vòng lặp Công việc của AI (AI Work Loop)

```mermaid
graph TD
    A[Bắt đầu Session] --> B(Đọc docs/AI_HANDOFF_STATE.md)
    B --> C{Nhận Yêu cầu từ User}
    C --> D[Phân tích Code & Đọc Skill]
    D --> E[Viết Code & Comment giải thích]
    E --> F[Cập nhật / Viết tài liệu Docs]
    F --> G[Kiểm thử bằng Skill qc-uat]
    G --> H[Ghi Log AI (Dual Logging)]
    H --> I[Báo cáo Hoàn thành cho User]
```
