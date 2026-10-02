# Kiến trúc và Cấu trúc Dự án (Project Structure)

Dự án này là một hệ thống AI Assistant cá nhân, được tổ chức theo mô hình Monorepo chứa cả frontend và backend, cùng với các thư mục quản lý tài liệu, dữ liệu và thiết lập cho AI (Agentic Coding).

## 📂 Tổng quan thư mục gốc

- **`apps/`**: Chứa mã nguồn chính của ứng dụng.
  - **`apps/web/`**: Frontend xây dựng bằng Next.js (App Router), React, TailwindCSS. Đây là giao diện người dùng chính (hiển thị danh sách task, lịch sử duyệt web, biểu đồ dữ liệu, v.v.).
  - **`apps/core/`**: Backend xây dựng bằng Python (FastAPI/SQLAlchemy). Xử lý logic nghiệp vụ, quản lý database, tương tác với các mô hình AI hoặc các logic phức tạp khác.

- **`data/`**: Thư mục lưu trữ dữ liệu (thường là các file JSON như `chrome-history.json`, `builder-data.json`, v.v.). Đây là nơi hệ thống trích xuất và đọc dữ liệu.

- **`docs/`**: Chứa các tài liệu thiết kế, hướng dẫn (ví dụ: `AI_HANDOFF_STATE.md`, tài liệu này). Giúp theo dõi quá trình phát triển, trạng thái dự án và quy trình làm việc.

- **`scripts/`**: Chứa các bash script hỗ trợ (như `release.sh` để deploy hoặc các tool tự động hoá khác).

- **`.kiro/steering/`**: Chứa các file **Steering Rules** (ví dụ: `comment-style.md`). Đây là những định nghĩa/quy tắc giúp định hướng cách AI phản hồi, cách AI viết code, comment và tài liệu trong lúc lập trình.

- **`patch_*.py` / `fix_*.py`**: Các đoạn script nhỏ tạm thời được sinh ra trong quá trình AI fix bug, cập nhật hoặc cào dữ liệu nhanh. (Những file này thường mang tính chất scratchpad tạm thời).

- **`infra/`** / **`docker-compose*.yml`**: Các tệp thiết lập hạ tầng Docker (Local / Prod) dùng để chạy toàn bộ stack dự án.

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
