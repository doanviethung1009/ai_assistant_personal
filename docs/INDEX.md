# Bản đồ tài liệu: đọc gì trước

> Repo có hơn 40 tài liệu. Bạn **không cần đọc hết**. Chọn đúng vai của bạn ở mục 1, đọc theo thứ tự, bỏ qua phần còn lại.

## 1. Chọn đường đọc theo vai

| Bạn là... | Đọc theo thứ tự | Mất khoảng |
|---|---|---|
| **Người dùng app** (nhập task, ghi chú) | `huong-dan-su-dung.md` | 10 phút |
| **Dev mới vào dự án** | `README.md` → `PROJECT_STRUCTURE.md` → `project-review.md` → `CI_AND_TESTING.md` | 30 phút |
| **Người dùng Claude Code** để làm việc | `CLAUDE_CLI_QUICKSTART.md` → `MULTI_AGENT_SYSTEM.md` → `MULTI_AGENT_TRIAL.md` | 30 phút |
| **AI agent mới nhận việc** | `AI_HANDOFF_STATE.md` → `NEW_AGENT_ONBOARDING.md` → `project-review.md` | 5 phút |
| **Người vận hành / triển khai** | `deploy-runbook.md` → `DOCKER_ARCHITECTURE.md` → `git-workflow.md` | 30 phút |
| **Thiết kế tính năng mới** | `TARGET_ARCHITECTURE.md` → `specs/_TEMPLATE.md` → `specs/note-archive.md` (ví dụ thật) | 20 phút |

## 2. Các tài liệu hay bị nhầm lẫn: cái nào là bản chính

Nhiều tài liệu nói về AI agent vì dự án dùng nhiều IDE và nhiều thế hệ cấu hình. Dùng bảng này để chọn.

| Bạn muốn... | Đọc (bản chính) | Còn lại là gì |
|---|---|---|
| Biết hệ multi-agent hoạt động thế nào, gõ gì để dùng | **`MULTI_AGENT_SYSTEM.md`** | `MULTI_AGENT_WORKFLOW.md` là kịch bản demo kiểu "đóng vai" cho IDE không có subagent (giữ làm tham khảo) |
| Xem luồng đó chạy thật, lỗi gì bắt được | **`MULTI_AGENT_TRIAL.md`** | `AI_REAL_WORLD_EXAMPLE.md` là case study cũ (Vault, Portal), viết theo kiểu "đóng vai" |
| Chạy Claude Code lần đầu | **`CLAUDE_CLI_QUICKSTART.md`** | `CLAUDE_OPERATING_GUIDE.md` (dài ~1000 dòng) là tài liệu cơ chế nạp context, chỉ đọc khi cần đào sâu |
| Dùng Codex | `CODEX_OPERATING_GUIDE.md` | Chỉ liên quan khi dùng OpenAI Codex |
| Biết AI phải làm gì khi bắt đầu session | **`NEW_AGENT_ONBOARDING.md`** và `AI_HANDOFF_STATE.md` | `AI_AGENT_GUIDE.md` mô tả cấu trúc `.agents/` |
| Viết prompt giao việc | `AGENT_PROMPT_EXAMPLES.md` | Prompt theo từng tình huống nằm trong `MULTI_AGENT_SYSTEM.md` mục 5 |
| Tự tạo thêm rule, skill, hook | `CREATE_AI_CUSTOMIZATIONS.md` | |
| Biết quy trình phát triển sản phẩm 6 bước | `PRODUCT_DEVELOPMENT_LIFECYCLE.md` | |
| Biết luật code | `.agents/rules/*.md` (xem nhóm "Quy ước Code" trên tab Tài liệu) | `AGENTS.md` là luật chung cho mọi agent |

## 3. Tài liệu theo nhóm (khớp với tab Tài liệu trên web)

1. **Bắt đầu:** hướng dẫn sử dụng, README, cấu trúc dự án, quy trình phát triển (PDLC).
2. **Làm việc với AI Agent:** Quickstart, hệ thống multi-agent, ví dụ thực chiến, prompt mẫu, onboarding, cẩm nang Claude và Codex.
3. **Quy ước Code & Rules:** luật backend, web, comment, nhật ký AI, bối cảnh dự án.
4. **Kỹ năng AI (Skills):** commit, thêm entity, QC/UAT. Các skill khác nằm trong `.agents/skills/`.
5. **Kiến trúc & Dữ liệu:** blueprint, kiến trúc mục tiêu, mẫu kiến trúc, lưu trữ dữ liệu, Vault, API, Jira.
6. **Spec thiết kế:** spec thật `note-archive.md` và bản mẫu viết tay `EXAMPLE-note-archive.md`.
7. **DevOps & Triển khai:** Git flow, deploy, Docker, CI và test, vận hành.

## 4. Tài liệu không cần đọc (chỉ để tra cứu)

- `ai_logs.md`: nhật ký các lần AI làm việc, chỉ thêm vào cuối, không đọc từ đầu.
- `AI_HANDOFF_STATE.md`: AI đọc khi bắt đầu session; người đọc nếu cần biết trạng thái hiện tại.

## 5. Quy ước khi thêm tài liệu mới

- Đặt file ở `docs/` (không chia thư mục con: `AGENTS.md`, rule và hook đang trỏ cứng `docs/<TÊN>.md`).
- **Đăng ký vào `apps/web/lib/docs.ts`** và chọn đúng nhóm ở mục 3; không đăng ký thì không hiện trên web.
- Có tài liệu cùng chủ đề rồi thì **sửa bản đó**, đừng thêm bản thứ hai. Nếu bắt buộc có hai bản, thêm một dòng vào bảng mục 2 để nói bản nào là chính.
