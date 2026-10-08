# Kiến trúc và Cấu trúc Dự án (Project Structure)

Dự án này là một hệ thống AI Assistant cá nhân, được tổ chức theo mô hình Monorepo chứa cả frontend và backend, cùng với các thư mục quản lý tài liệu, dữ liệu và thiết lập cho AI (Agentic Coding).

## 📂 Cây thư mục gốc (Directory Tree)

Dưới đây là sơ đồ tổng quan của dự án. Mọi logic chính đều tập trung trong thư mục `apps/`.

```text
ai_assistant_personal/
├── CLAUDE.md          # 🚪 Điểm vào của Claude Code (import AGENTS.md)
├── AGENTS.md          # 📜 Luật chung cho mọi AI agent
├── Makefile           # 🔧 Mọi thao tác vận hành (make = xem danh sách)
├── docker-compose*.yml# 🐳 Stack dev / prod / LAN
├── .agents/           # 🤖 Nguồn thật của AI config (dùng chung nhiều IDE)
│   ├── rules/         #    Luật code, nạp theo file đang sửa
│   ├── skills/        #    Quy trình đóng gói (commit, migration, QC...)
│   └── roles/         #    9 vai "đóng vai" cho IDE không có subagent
├── .claude/           # 🧠 Cấu hình riêng Claude Code
│   ├── agents/        #    Subagent thật (architect, backend-dev, ... security-auditor)
│   ├── hooks/         #    guard-bash.sh, no-patch-scripts.sh
│   ├── settings.json  #    Quyền allow/ask/deny + hook
│   ├── rules  ──►  ../.agents/rules     (symlink)
│   └── skills ──►  ../.agents/skills    (symlink)
├── .codex/            # Cấu hình cho OpenAI Codex
├── apps/              # 💻 Mã nguồn chính của hệ thống
│   ├── core/          # ⚙️ Backend (Python / FastAPI / SQLAlchemy / Alembic)
│   └── web/           # 🎨 Frontend (Next.js / React / Tailwind)
├── data/              # 🗄️ Dữ liệu chạy thật (JSON, gitignore, KHÔNG commit)
├── docs/              # 📚 Tài liệu (Markdown), đăng ký ở apps/web/lib/docs.ts
│   └── specs/         #    Spec của architect: _TEMPLATE.md và ví dụ EXAMPLE-*.md
├── infra/             # 🏗️ Cấu hình hạ tầng (postgres, litellm, monitoring)
├── scripts/           # 🛠️ Script vận hành
│   ├── *.sh, *.js     #    Tiện ích đang dùng (release, bootstrap, add-ai-log...)
│   ├── checks/        #    Script kiểm thử chạy được nhiều lần (vault-crypto-check.ts)
│   ├── git-hooks/     #    Hook kiểm tra commit message
│   └── patches/       #    Script một lần, CHỈ khi thật cần; lịch sử đã chạy ở archive/
└── task/              # 📎 File Excel mẫu phiếu Jira (không liên quan tới code chạy)
```

### 🎨 Frontend (`apps/web/`)
Giao diện người dùng chính được xây dựng bằng Next.js App Router (React, TailwindCSS).

| Thư mục / File quan trọng | Chức năng chính (Dev logic) | Ghi chú |
|---------------------------|-----------------------------|---------|
| `app/layout.tsx` | Root layout bọc toàn bộ ứng dụng, nạp CSS và Font. | |
| `app/page.tsx` | Trang chủ (Dashboard chính). | |
| `app/globals.css` | Chứa toàn bộ Design System, biến CSS (colors, spacing, animation). | Sửa theme ở đây. |
| `app/[module]/page.tsx` | Các trang chức năng (tasks, notes, projects, v.v.). | Ví dụ: `app/tasks/page.tsx` |
| `components/` | Các UI Components dùng chung (Button, Table, Markdown...). | Độc lập, tái sử dụng cao. |
| `lib/` | Hàm tiện ích client/server, thao tác dữ liệu. | Chứa `api.ts`, `format.ts`. |
| `actions*.ts` | Các Server Actions (Next.js) thực thi logic phía server. | Gọi thẳng từ component thay cho API REST. |
| `next.config.mjs` | Cấu hình webpack, env, routing cho Next.js. | |

### ⚙️ Backend (`apps/core/`)
API Server xử lý logic nghiệp vụ và tương tác Database.

| Thư mục / File quan trọng | Chức năng chính (Dev logic) | Ghi chú |
|---------------------------|-----------------------------|---------|
| `app/main.py` | Entrypoint khởi tạo app FastAPI, đăng ký middleware, CORS. | Nơi chạy `uvicorn`. |
| `app/core/config.py` | Quản lý biến môi trường (Pydantic BaseSettings). | Đọc từ `.env`. |
| `app/db/` | Cấu hình kết nối DB, session và base model SQLAlchemy. | |
| `app/models/` | Định nghĩa các bảng Database (Tasks, Notes, Projects). | Ánh xạ trực tiếp xuống DB. |
| `app/schemas/`| Định nghĩa Pydantic models để validate Input/Output API. | Đảm bảo an toàn dữ liệu. |
| `app/api/v1/` | Định nghĩa các endpoint REST API (Routes). | Chứa file như `tasks.py`, `notes.py`. |
| `app/services/`| Logic nghiệp vụ thuần (CRUD, đồng bộ, tính toán). | Không dính dáng trực tiếp tới HTTP Request. |
| `alembic/` | Thư mục quản lý phiên bản Database (Migrations). | Dùng lệnh `alembic upgrade head`. |

### Các thư mục hỗ trợ khác
- **`data/`**: Chứa các file `*.json` sinh ra từ quá trình cào dữ liệu.
- **`docs/`**: Toàn bộ tài liệu mô tả kiến trúc, hướng dẫn sử dụng và API.
- **`scripts/`**: Script vận hành (như `release.sh`). `scripts/checks/` là script kiểm thử dùng lại được. `scripts/patches/` chỉ dành cho script một lần *thật sự* cần thiết; 71 script `patch_*`/`fix_*` cũ đã chạy xong nằm ở `scripts/patches/archive/` (không chạy lại). Claude Code bị hook chặn tạo `patch_*`/`fix_*` mới, hãy dùng Edit trực tiếp.

## 🤖 Các file nào tự động nạp (load) khi Prompt AI?

Trong hệ thống Antigravity (hoặc khi dùng AI IDE), các file **Steering / Rules** sẽ được tự động nạp tuỳ vào nội dung bạn thao tác:

1. **Global/Workspace Rules**: Các file nằm trong thư mục `.kiro/steering/` (hoặc `.agents/rules/`). 
   - *Ví dụ*: File `.kiro/steering/comment-style.md` có khai báo block `fileMatchPattern: ["apps/**/*.py", "apps/**/*.ts", "apps/**/*.tsx"]`. Điều này nghĩa là: **Bất cứ khi nào bạn hoặc AI xem/chỉnh sửa các file `.py`, `.ts`, `.tsx`, quy tắc trong file này sẽ TỰ ĐỘNG được tiêm vào bộ não (context) của AI**. Do đó AI sẽ luôn biết cách tự comment code hay tự document.
2. **Skills**: Nằm trong thư mục `.agents/skills/` (nếu có). AI sẽ đọc mô tả của skill và tự nạp hướng dẫn nếu thấy request của bạn phù hợp.
3. **Current Context**: Các file bạn đang mở (Active Tabs) hoặc thư mục bạn đang trỏ chuột, AI sẽ nạp chúng để lấy ngữ cảnh trực tiếp.

## 📝 Tóm lược quy trình làm việc

- **Phát triển UI/Tính năng web**: Làm việc chủ yếu trong `apps/web/app/` (các page/router), `apps/web/components/` (UI), và `apps/web/lib/` (logic như gọi core API, định dạng ngày giờ).
- **Phát triển Backend/API**: Làm việc trong `apps/core/`.
- **Thao tác Dữ liệu**: Dữ liệu lấy về (từ file Excel, History) sẽ lưu ra JSON vào thư mục `data/` rồi frontend sẽ đọc.
- **Tài liệu**: Mỗi khi làm xong chức năng lớn, AI sẽ tự cập nhật vào thư mục `docs/`.

---

## 🛠 Hướng dẫn tuỳ chỉnh AI (Rules & Skills) chuẩn hệ thống

Nếu bạn không muốn sử dụng thư mục `.kiro/` (vốn là chuẩn riêng), hệ thống AI (Antigravity/Gemini) hỗ trợ **chuẩn cấu hình gốc** tại thư mục `.agents/` nằm ở root dự án. 

Quy ước chuẩn khi bạn muốn viết Document/Prompt để ép AI làm theo ý mình:

### 1. Viết Rules (Quy tắc hành xử, coding style)
Tạo thư mục `.agents/rules/` và thêm các file Markdown (`.md`).
- **Cách dùng**: Viết các chỉ thị như "Luôn dùng JSDoc", "Luôn phân trang", "Luôn viết tiếng Việt".
- **File đặc biệt**: Bạn có thể tạo file `GEMINI.md` hoặc `AGENTS.md` ngay ngoài root dự án. AI sẽ luôn đọc file này trước tiên để lấy chỉ thị toàn cục (tương đương System Prompt).

### 2. Tạo Skills (Kỹ năng đặc thù cho AI)
Nếu có những quy trình lặp đi lặp lại phức tạp (ví dụ: quy trình deploy, quy trình review code, tạo tính năng mới theo một format mẫu), hãy tạo Skill.
- **Vị trí**: `.agents/skills/<ten_skill>/`
- **Cấu trúc**: Bắt buộc phải có file `SKILL.md` bên trong thư mục đó.
- **Cách dùng**: Trong `SKILL.md`, dùng YAML frontmatter để khai báo:
  ```markdown
  ---
  name: "deploy-prod"
  description: "Quy trình đưa code từ uat lên production"
  ---
  
  # Hướng dẫn chi tiết
  1. Chạy lệnh A
  2. Cập nhật file B
  ```
- **Kích hoạt**: Mỗi khi bạn gõ prompt có liên quan tới từ khoá (ví dụ "deploy lên prod đi"), AI sẽ nhận diện được Skill `deploy-prod`, tự động nhảy vào đọc file `SKILL.md` đó rồi làm theo từng bước như một checklist, không bao giờ quên sót.

### 3. Bí quyết viết Prompt và Document hiệu quả cho AI
- **Rõ ràng và có điều kiện**: Thay vì nói chung chung, hãy dùng "NẾU... THÌ...". *(Ví dụ: "NẾU danh sách có quá 50 dòng, THÌ bắt buộc phải có phân trang server-side".)*
- **Khai báo fileMatchPattern**: Giống như file `comment-style.md`, bạn có thể đặt đoạn YAML ở đầu file MD để ép AI chỉ đọc rule này khi đụng vào đúng loại file cụ thể, giúp tiết kiệm bộ nhớ cho AI:
  ```yaml
  ---
  inclusion: fileMatch
  fileMatchPattern: ["*.tsx", "*.ts"]
  ---
  ```
- **Cung cấp ví dụ (Few-shot)**: AI học rất nhanh qua ví dụ. Trong file rule, luôn đưa ra 1 ví dụ "Code Sai" và 1 ví dụ "Code Đúng".
