# Kiến trúc và Cấu trúc Dự án (Project Structure)

Dự án này là một hệ thống AI Assistant cá nhân, được tổ chức theo mô hình Monorepo chứa cả frontend và backend, cùng với các thư mục quản lý tài liệu, dữ liệu và thiết lập cho AI (Agentic Coding).

## 📂 Cây thư mục gốc (Directory Tree)

Dưới đây là sơ đồ tổng quan của dự án. Mọi logic chính đều tập trung trong thư mục `apps/`.

```text
ai_assistant_personal/
├── .agents/           # 🤖 Cấu hình cho AI (Rules, Skills, Prompts)
├── apps/              # 💻 Mã nguồn chính của hệ thống
│   ├── core/          # ⚙️ Backend (Python / FastAPI / SQLAlchemy)
│   └── web/           # 🎨 Frontend (Next.js / React / Tailwind)
├── data/              # 🗄️ Nơi lưu trữ dữ liệu trích xuất (JSON files)
├── docs/              # 📚 Tài liệu dự án (Markdown)
├── infra/             # 🏗️ Cấu hình hạ tầng (Docker, Server)
└── scripts/           # 🛠️ Script tiện ích & Các patch sửa lỗi tạm
```

### 🎨 Frontend (`apps/web/`)
Giao diện người dùng chính được xây dựng bằng Next.js App Router.

| Thư mục/File | Chức năng chính | Ghi chú |
|--------------|-----------------|---------|
| `app/` | Chứa các trang (Pages) như `/history`, `/tasks`. | Mọi route web đều nằm ở đây. |
| `components/`| Chứa các UI Components dùng chung (Button, Table). | Thiết kế độc lập, tái sử dụng. |
| `lib/` | Chứa logic xử lý, cấu hình (như đọc Markdown, cào Chrome History). | |
| `actions*.ts`| Các Server Actions để giao tiếp trực tiếp với Backend. | |

### ⚙️ Backend (`apps/core/`)
Xử lý logic nghiệp vụ và tương tác với cơ sở dữ liệu.

| Thư mục | Chức năng chính | Ghi chú |
|---------|-----------------|---------|
| `api/v1/` | Định nghĩa các endpoint REST API (Routes). | Điểm tiếp nhận request từ Web. |
| `models/` | Định nghĩa cấu trúc bảng Database (SQLAlchemy). | Không dùng `create_all`, dùng Alembic. |
| `services/` | Xử lý logic nghiệp vụ, tính toán. | Ví dụ: Logic đồng bộ, xử lý soft delete. |

### Các thư mục hỗ trợ khác
- **`data/`**: Chứa các file `*.json` sinh ra từ quá trình cào dữ liệu (như `chrome-history.json`).
- **`docs/`**: Toàn bộ tài liệu mô tả kiến trúc, hướng dẫn sử dụng và API.
- **`scripts/`**: Chứa các bash script hỗ trợ (như `release.sh`) và đặc biệt là thư mục con `scripts/patches/` chứa các script sửa lỗi tạm thời (`patch_*.py`).

## 🤖 Các file nào tự động nạp (load) khi Prompt AI?

Trong hệ thống Antigravity (hoặc khi dùng AI IDE), các file **Steering / Rules** sẽ được tự động nạp tuỳ vào nội dung bạn thao tác:

1. **Global/Workspace Rules**: Các file nằm trong thư mục `.kiro/steering/` (hoặc `.agents/rules/`). 
   - *Ví dụ*: File `.kiro/steering/comment-style.md` có khai báo block `fileMatchPattern: ["apps/**/*.py", "apps/**/*.ts", "apps/**/*.tsx"]`. Điều này nghĩa là: **Bất cứ khi nào bạn hoặc AI xem/chỉnh sửa các file `.py`, `.ts`, `.tsx`, quy tắc trong file này sẽ TỰ ĐỘNG được tiêm vào bộ não (context) của AI**. Do đó AI sẽ luôn biết cách tự comment code hay tự document.
2. **Skills**: Nằm trong thư mục `.agents/skills/` (nếu có). AI sẽ đọc mô tả của skill và tự nạp hướng dẫn nếu thấy request của bạn phù hợp.
3. **Current Context**: Các file bạn đang mở (Active Tabs) hoặc thư mục bạn đang trỏ chuột, AI sẽ nạp chúng để lấy ngữ cảnh trực tiếp.

## 📝 Tóm lược quy trình làm việc

- **Phát triển UI/Tính năng web**: Làm việc chủ yếu trong `apps/web/app/` (các page/router), `apps/web/components/` (UI), và `apps/web/lib/` (logic như cào chrome history).
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
