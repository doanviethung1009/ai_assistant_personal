# Ví dụ Thực chiến: Xây dựng Hệ sinh thái Multi-App & Vault

> **Case study cũ**, viết theo kiểu "đóng vai" nhiều agent. Muốn xem luồng subagent chạy thật với lỗi và số liệu: `MULTI_AGENT_TRIAL.md`. Xem `INDEX.md` để biết nên đọc gì.

Tài liệu này là một **Case Study (Bài học thực tế)** dành cho các thành viên trong dự án. Nó minh hoạ cách áp dụng cơ chế Multi-Agent (Nhiều AI phối hợp) với 8 Roles để nâng cấp hệ thống từ Phase 1 (Local JSON) lên Phase 2 & 3: **Hệ sinh thái Đa Ứng dụng (Multi-App Portal)** kết hợp **Két bảo mật (Vault)**.

---

## Bối cảnh (Context)
Dự án của chúng ta đang là một Monorepo (`apps/web` và `apps/core`). 
Mục tiêu tiếp theo là:
1. Đưa hệ thống lên môi trường Docker chuyên nghiệp (PostgreSQL + Redis).
2. Xây dựng **Portal** quản lý người dùng và phân quyền.
3. Tạo tính năng **Vault (Két bảo mật)** áp dụng mã hóa đầu cuối (Zero-Knowledge) để lưu trữ API Keys/Mật khẩu siêu nhạy cảm.

Thay vì tự mình gõ code, bạn (trong vai trò Nhạc trưởng / Product Owner) sẽ "điều binh khiển tướng" dàn Agent như sau:

---

## 📐 Bước 1: Khởi tạo Kiến trúc (Software Architect)
Mọi Epic lớn đều phải bắt đầu từ bản vẽ. Bạn không bao giờ gọi Backend hay Frontend trước.

**Bạn (Prompt):**
> *"Đóng vai `@.agents/roles/software-architect.md`. Mục tiêu của chúng ta là xây dựng tính năng Vault (Zero-Knowledge). Hãy phân tích luồng mã hoá dữ liệu tại Client (Browser) và luồng lưu trữ Ciphertext tại Backend (Postgres). Hãy vẽ sơ đồ Sequence Diagram bằng Mermaid và cập nhật vào `docs/TARGET_ARCHITECTURE.md`."*

**AI Phản hồi:** Architect phân tích và đưa ra bản vẽ cho thấy Trình duyệt sẽ dùng thuật toán `PBKDF2` sinh khoá từ Master Password, sau đó mã hoá bằng `AES-256-GCM` trước khi đẩy lên API. Backend chỉ nhận được một chuỗi mã hoá vô nghĩa.

---

## 🗄️ Bước 2: Thiết kế Database (Database Architect)
Khi luồng đi đã rõ, cần người xây móng nhà.

**Bạn (Prompt):**
> *"Đóng vai `@.agents/roles/database-architect.md`. Architect đã chốt kiến trúc Vault. Hãy gọi skill `db-migration` để tạo ra một file Alembic migration mới. Tạo bảng `vault_items` chứa cột `id`, `user_id`, `ciphertext`, `nonce`, và `salt`. Lưu ý đánh index cho `user_id`."*

**AI Phản hồi:** DBA sinh ra file `versions/1234_create_vault_table.py` hoàn hảo, chuẩn cú pháp SQLAlchemy.

---

## ⚙️ Bước 3: Phát triển Backend & Xác thực (Backend + Security)
Tiếp theo là xây dựng các Endpoint. Đặc biệt tính năng này liên quan đến bảo mật nên cần cả Security Auditor.

**Bạn (Prompt):**
> *"Đóng vai `@.agents/roles/backend-engineer.md`. Hãy viết API `/api/v1/vault` để GET/POST dữ liệu vào bảng `vault_items`. Bắt buộc phải có dependency kiểm tra token JWT (Xác thực người dùng).*
> 
> *Sau đó, chuyển quyền cho `@.agents/roles/security-auditor.md` dùng skill `security-audit` rà soát lại xem API vừa viết có lỗi SQL Injection hay có trả nhầm dữ liệu của User A cho User B (Lỗi IDOR) hay không."*

**AI Phản hồi:** Backend viết xong API. Security Auditor nhảy vào test và phát hiện lỗi thiếu Check Owner (IDOR), tự động đề xuất vá lỗi bằng cách thêm `.where(user_id == current_user.id)`.

---

## 🎨 Bước 4: Xây dựng Giao diện (Frontend Engineer)
API đã có, giờ là lúc gắn "Mặt tiền".

**Bạn (Prompt):**
> *"Đóng vai `@.agents/roles/frontend-engineer.md`. Hãy code trang `/vault` trên Next.js. Đọc `docs/API_REFERENCE.md` để lấy payload. Yêu cầu giao diện theo phong cách Glassmorphism. Bắt buộc áp dụng thư viện `Web Crypto API` để thực hiện giải mã AES-256-GCM ngay trên Client. Cấm không được gửi Master Password xuống Server!"*

**AI Phản hồi:** Frontend sinh ra UI cực đẹp, viết logic xử lý ArrayBuffer cho mã hoá/giải mã mượt mà mà không làm rò rỉ dữ liệu lên mạng.

---

## 🐳 Bước 5: Đóng gói và DevOps (DevOps Engineer)
Code xong chạy tốt ở Local, giờ cần đưa lên môi trường Production.

**Bạn (Prompt):**
> *"Đóng vai `@.agents/roles/devops-engineer.md`. Chúng ta đang chuyển sang mô hình Multi-App. Hãy cập nhật file `docker-compose.prod.yml` gồm các container: Nginx (làm API Gateway), Next.js (Web), FastAPI (Core), Postgres và Redis. Bật rule bảo mật không cho expose port của Postgres ra ngoài (chỉ cho mạng nội bộ docker network)."*

**AI Phản hồi:** File `docker-compose.prod.yml` được cấu hình an toàn tuyệt đối, sử dụng Reverse Proxy của Nginx để điều phối luồng Multi-app.

---

## 👑 Bước 6: Nghiệm thu và Lên sóng (Tech Lead)
Tất cả Agent đã làm xong việc trên nhánh Feature (VD: `feat/vault-system`).

**Bạn (Prompt):**
> *"Đóng vai `@.agents/roles/tech-lead.md`. Toàn bộ luồng Vault và Multi-app Docker đã được code xong. Hãy dùng skill `pr-review` rà soát tổng thể lần cuối toàn bộ Source Code xem có lọt file `.env` rác hay vi phạm kiến trúc không. Nếu mọi thứ xanh (Green), hãy sinh `CHANGELOG.md` và Merge vào nhánh `main`."*

**AI Phản hồi:** Tech Lead duyệt qua toàn bộ Diff, xoá đi vài câu lệnh `console.log()` bỏ quên của Frontend, chốt Changelog và thực hiện Merge.

---

## 💡 Lời kết
Bằng cách vận hành như một "Nhạc trưởng", bạn đã chia một khối lượng công việc khổng lồ (Chuyển đổi Multi-App và Mã hoá E2EE) thành 6 mảnh ghép nhỏ, giao đúng người (Agent) đúng việc. 

Kết quả là tính năng **Vault (Két bảo mật)** được hoàn thành thần tốc nhưng chất lượng và bảo mật ngang ngửa một đội ngũ Kỹ sư Senior thật sự! Hệ thống của bạn đã sẵn sàng cho bất kỳ quy mô nào trong tương lai.
