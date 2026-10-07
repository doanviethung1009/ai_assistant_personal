# Cẩm nang AI Agent: cấu trúc, nền tảng, prompt mẫu

> File duy nhất trả lời ba câu: **cấu hình AI của dự án nằm ở đâu**, **mỗi công cụ (Claude, Codex, Cursor...) đọc cái gì**, và **gõ prompt thế nào cho hiệu quả**.
> Gộp từ ba tài liệu cũ (`AI_AGENT_GUIDE`, `AGENT_PROMPT_EXAMPLES`, phần nền tảng) để khỏi phải đọc ba nơi.
>
> Muốn đi sâu: `MULTI_AGENT_SYSTEM.md` (nhiều agent phối hợp), `CLAUDE_CLI_QUICKSTART.md` (Claude Code), `CREATE_AI_CUSTOMIZATIONS.md` (tự tạo rule, skill, hook), `NEW_AGENT_ONBOARDING.md` (việc AI phải làm khi bắt đầu session).

---

## 1. Cấu hình AI nằm ở đâu

Nguyên tắc **một gốc, nhiều nhánh**: luật viết một lần ở `.agents/` và `AGENTS.md`, mỗi công cụ chỉ có một file mỏng trỏ về đó.

```text
AGENTS.md                      Luật chung cho MỌI agent (nguồn chân lý)
CLAUDE.md                      Điểm vào của Claude Code, chỉ import AGENTS.md
.cursorrules                   Cầu nối cho Cursor/Windsurf, trỏ về AGENTS.md
.github/copilot-instructions.md  Cầu nối cho GitHub Copilot
.codex/config.toml             Cấu hình cho OpenAI Codex (đọc AGENTS.md native)

.agents/                       NGUỒN THẬT của cấu hình AI dùng chung
  ├── rules/                   Luật code, nạp theo file đang sửa
  ├── skills/                  Quy trình đóng gói (10 skill: commit, migration, QC...)
  └── roles/                   9 vai "đóng vai" cho IDE không có subagent

.claude/                       Riêng cho Claude Code
  ├── agents/                  6 subagent thật (architect, backend-dev, ... security-auditor)
  ├── hooks/                   Chặn lệnh nguy hiểm, chặn script patch_*
  ├── settings.json            Quyền allow/ask/deny + hook
  ├── rules  ──► ../.agents/rules    (symlink, không có bản sao thứ hai)
  └── skills ──► ../.agents/skills   (symlink)
```

Sửa luật hay skill thì sửa ở `.agents/`. **Đừng** sửa qua `.claude/rules` hay `.claude/skills` (chỉ là symlink).

### Rule được nạp thế nào

Mỗi file trong `.agents/rules/` có frontmatter khai báo khi nào nạp, và khai **cả hai** kiểu để mọi công cụ hiểu:

```yaml
---
paths:                       # Claude Code đọc khoá này
  - "apps/core/**"
  - "apps/**/*.py"
inclusion: fileMatch         # Kiro / Antigravity đọc hai khoá này
fileMatchPattern: ["apps/core/**/*", "apps/**/*.py"]
---
```

Nghĩa là: sửa file khớp mẫu thì luật đó tự nạp vào ngữ cảnh của AI, không cần nhắc trong prompt. Tạo ứng dụng mới khớp mẫu thì không phải cấu hình lại.

Cách viết rule hiệu quả: dùng cú pháp **NẾU ... THÌ ...**, có một ví dụ ✅ tốt và một ví dụ ❌ xấu. Hướng dẫn tạo rule, skill, hook từng bước: `CREATE_AI_CUSTOMIZATIONS.md`.

### Quy ước dọn dẹp thư mục

- Không để script rác ở thư mục gốc.
- Script vận hành (deploy, test, release) ở `scripts/`; script kiểm thử dùng lại được ở `scripts/checks/`.
- Script một lần thật sự cần thiết ở `scripts/patches/`; lịch sử cũ đã chạy xong ở `scripts/patches/archive/` (không chạy lại).
- Claude Code bị hook chặn tạo `patch_*` và `fix_*`: dùng Edit trực tiếp.
- Dữ liệu chạy thật ở `data/` (gitignore).

---

## 2. Mỗi công cụ đọc gì và dùng thế nào

| Công cụ | File nó đọc | Cách mở | Chi tiết |
|---|---|---|---|
| **Claude Code** (CLI, desktop) | `CLAUDE.md` → `AGENTS.md`, `.claude/` | `claude` ở thư mục gốc | `CLAUDE_CLI_QUICKSTART.md`, `CLAUDE_OPERATING_GUIDE.md` |
| **OpenAI Codex** (CLI, IDE) | `AGENTS.md` (native), `.codex/config.toml` | `codex` ở thư mục gốc | `CODEX_OPERATING_GUIDE.md` |
| **Cursor, Windsurf, Antigravity** | `.cursorrules` → `AGENTS.md` | Mở thư mục, dùng Composer/Chat | |
| **GitHub Copilot** | `.github/copilot-instructions.md` | Copilot Chat, gõ `@workspace` | Ít tự trị hơn nhưng vẫn theo luật |
| **ChatGPT / Claude Web** | Không quét được ổ cứng | Tạo Project/Custom GPT, dán nội dung `AGENTS.md` vào System Instructions | |

Chỉ **Claude Code** có subagent thật. Các công cụ còn lại dùng vai trong `.agents/roles/` bằng prompt "đóng vai". Bản đối chiếu vai và subagent: `MULTI_AGENT_SYSTEM.md` mục 3.

---

## 3. Prompt mẫu

Dự án đã có Rules và Skills, nên **không cần prompt dài**: chỉ cần *bối cảnh + trỏ file + gọi skill + ép rule*.

> **Công thức:** (1) Đang bị gì, muốn gì. (2) File liên quan nếu biết. (3) "Hãy dùng skill ...". (4) "Nhớ tuân thủ rule ...".

### 3.1. Làm chức năng mới xuyên suốt DB, API, web

> "Làm tính năng Quản lý Khách hàng (Customer): tên, email, số điện thoại. Dùng skill `add-entity` để làm toàn bộ từ Database, Backend API đến Frontend."

Skill `add-entity` dẫn AI qua 15 bước (model, schema, endpoint, docs, giao diện) nên không bỏ sót bước. Việc chạm từ hai tầng trở lên: dùng luồng architect → dev → reviewer trong `MULTI_AGENT_SYSTEM.md`.

### 3.2. Sửa lỗi hoặc refactor

> "Trang Danh sách Project không hiện đủ dữ liệu. Kiểm `apps/web/app/projects/page.tsx` và API tương ứng. Tuân thủ `web-conventions` và nguyên tắc phân trang."

Rule `web-conventions` tự nạp khi sửa file trong `apps/web/`, nên AI không tự cài thêm thư viện bừa.

### 3.3. Commit

> "Tôi test xong rồi. Dùng skill `git-commit` đóng gói các thay đổi."

Skill bắt buộc dùng Conventional Commits, kiểm danh sách file, và **không push khi chưa hỏi bạn**.

### 3.4. Tìm lỗi hệ thống

> "API `/api/v1/tasks` trả lỗi 500. Đọc log container `api` (`make logs-api`), tìm nguyên nhân, sửa và ghi comment giải thích vì sao lỗi, theo `comment-style`."

Dùng `make` thay vì tự viết lệnh `docker compose`; xem danh sách bằng `make`.

### 3.5. Review code

> "Review thay đổi của nhánh hiện tại so với `main`. Đối chiếu `backend-conventions`, `web-conventions` và `PROJECT_STRUCTURE.md`."

Với Claude Code: "Dùng `code-reviewer` review nhánh hiện tại" (context sạch, chỉ đọc, đáng tin hơn tự review).

### 3.6. Gọi đích danh một vai (IDE không có subagent)

> "Đóng vai `@.agents/roles/database-architect.md`. Tạo bảng `Vault`, rồi chạy skill `db-migration` để sinh migration an toàn. Không sửa giao diện."

> "Đóng vai `@.agents/roles/qa-tester.md`, chạy skill `pr-review` soát nhánh `feat/new-api` trước khi tôi merge."

Danh sách 9 vai: `tech-lead`, `software-architect`, `security-auditor`, `frontend-engineer`, `backend-engineer`, `qa-tester`, `database-architect`, `devops-engineer`, `ai-rag-engineer`.

### 3.7. Tiếp tục ở session mới

> "Đọc `docs/AI_HANDOFF_STATE.md` rồi tóm tắt trạng thái hiện tại cho tôi."

---

## 4. Lỗi thường gặp khi giao việc cho AI

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| AI không theo luật dự án | Chưa nạp ngữ cảnh | Trỏ AI vào `docs/NEW_AGENT_ONBOARDING.md` |
| AI tự cài thư viện lạ | Prompt không nhắc rule | Thêm "tuân thủ `web-conventions`" hoặc `backend-conventions` |
| AI làm xong nhưng không cập nhật docs, không ghi log | Quên bước cuối | Nhắc luật 3.3, 3.4, 3.10 trong `AGENTS.md` |
| AI sửa file ngoài phạm vi | Không có spec rõ ràng | Với việc lớn, bắt đầu bằng spec trong `docs/specs/` |
| AI push khi chưa được phép | Luật chỉ là lời dặn | Claude Code đã chặn bằng quyền `ask`; công cụ khác thì nhắc rõ "không push" |
