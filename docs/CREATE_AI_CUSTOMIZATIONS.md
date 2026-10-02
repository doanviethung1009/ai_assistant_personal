# Cẩm nang Thiết lập Agent Customizations (Rules, Skills, Hooks)

Hệ thống AI Agent trong dự án này (như Antigravity) cung cấp một bộ công cụ mạnh mẽ gọi là **Customizations** để bạn tuỳ chỉnh, "dạy" và điều khiển hành vi của AI một cách tự động. 

Tài liệu này hướng dẫn chi tiết cách tạo và cấu hình các thành phần này trong thư mục `.agents/`.

---

## 1. Rules (Quy tắc tự động)
**Rule** là các file Markdown chứa định hướng (Coding convention, quy trình) được AI **tự động nạp** dựa trên ngữ cảnh (nghĩa là dựa trên file bạn đang mở, hoặc thư mục bạn đang thao tác).

**Quy trình tạo một Rule mới:**
1. Tạo một file `.md` trong thư mục `.agents/rules/` (Ví dụ: `api-rules.md`).
2. Luôn bắt đầu file bằng một đoạn YAML (Frontmatter) để định nghĩa điều kiện kích hoạt:
   ```yaml
   ---
   inclusion: fileMatch
   fileMatchPattern: ["apps/core/api/**/*.py"]
   ---
   ```
   *Lưu ý:* Có thể dùng list (mảng) glob pattern để bao phủ nhiều trường hợp (vd: ứng dụng sinh ra trong tương lai).
3. Viết luật theo cú pháp **Mệnh lệnh / Điều kiện**:
   - Dùng cấu trúc: `NẾU [Tình huống] THÌ BẮT BUỘC [Hành động]`.
   - Cung cấp mẫu Code chuẩn (Good) và Code sai (Bad) để AI bắt chước.
   - Giữ luật thật cô đọng, tránh giải thích dài dòng.

---

## 2. Skills (Kỹ năng thao tác nhiều bước)
**Skill** là một cẩm nang/checklist hành động phức tạp. Khác với Rule (nạp ẩn và tự động), Skill thường được nạp khi User yêu cầu trực tiếp qua Prompt (ví dụ: *"Dùng skill deploy"*).

**Quy trình tạo một Skill mới:**
1. Tạo một thư mục con trong `.agents/skills/` (Ví dụ: `.agents/skills/deploy-aws/`).
2. **Bắt buộc:** Tạo file `SKILL.md` bên trong thư mục vừa tạo.
3. Thêm YAML Frontmatter định nghĩa meta-data của Skill:
   ```yaml
   ---
   name: "deploy-aws"
   description: "Quy trình 5 bước để build và đẩy Docker Image lên AWS ECR."
   ---
   ```
4. Viết nội dung hướng dẫn từng bước:
   - Đánh số thứ tự rõ ràng (1, 2, 3...).
   - Liệt kê chính xác các câu lệnh shell cần chạy.
   - Chỉ định rõ AI cần phải làm gì nếu một bước báo lỗi (Ví dụ: *"Nếu lệnh push lỗi, hãy dừng lại và báo cho user biết"*).
5. (Tuỳ chọn) Tạo thêm thư mục `scripts/` hoặc `templates/` bên trong folder của skill nếu Skill đó cần gọi đến các bash script phức tạp.

---

## 3. Hooks (Lệnh móc nối vòng đời)
**Hooks** cho phép bạn tự động thực thi các bash commands mỗi khi một sự kiện cụ thể xảy ra trong vòng đời của Agent (Ví dụ: Ngay khi Agent vừa khởi động lên).

**Quy trình tạo Hooks:**
1. Tạo file `.agents/hooks.json`.
2. Khai báo các sự kiện (events). Hiện tại hệ thống hỗ trợ sự kiện `on_startup`.
   ```json
   {
     "on_startup": [
       {
         "command": "make setup-env",
         "description": "Tự động cài đặt biến môi trường khi AI bật lên"
       },
       {
         "command": "git fetch origin",
         "description": "Kéo lịch sử Git mới nhất"
       }
     ]
   }
   ```
3. Mỗi khi bạn mở một cửa sổ chat mới với AI, các lệnh này sẽ được chạy ngầm trước để dọn đường cho AI làm việc hiệu quả.

---

## 4. Plugins & MCP Servers (Mở rộng công cụ)
Nếu bạn cần AI đọc trực tiếp dữ liệu từ Database (Postgres), lấy data từ Jira, hay đọc file từ Google Drive, bạn cần tới MCP (Model Context Protocol).

**Quy trình cấu hình MCP Server:**
1. Tạo thư mục `.agents/plugins/my-jira-plugin/`.
2. Tạo file `mcp_config.json` định nghĩa server:
   ```json
   {
     "mcpServers": {
       "postgres": {
         "command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://user:pass@localhost/db"]
       }
     }
   }
   ```
3. Khi AI khởi động, nó sẽ nạp plugin này và tự động sở hữu bộ công cụ (Tools) có khả năng query trực tiếp vào Database Postgres của bạn để hỗ trợ bạn debug.

---

## Tóm tắt: Khi nào dùng cái nào?
- **Bạn muốn AI luôn code theo chuẩn?** ➡️ Dùng **Rules** (`.agents/rules/`).
- **Bạn muốn nhờ AI làm một công việc lặp đi lặp lại?** ➡️ Dùng **Skills** (`.agents/skills/`).
- **Bạn muốn chuẩn bị sẵn môi trường khi gọi AI?** ➡️ Dùng **Hooks** (`.agents/hooks.json`).
- **Bạn muốn AI giao tiếp được với Slack/Jira/DB?** ➡️ Dùng **MCP Plugins** (`.agents/plugins/`).
