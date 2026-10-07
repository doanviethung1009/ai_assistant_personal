# Đề xuất Kiến trúc Mục tiêu (Target Architecture)

Tài liệu này trình bày mô hình kiến trúc đích (End-state Architecture) dành cho hệ thống **Builder AI Assistant** khi tiến tới hoàn thiện cả 3 mảng: Task Management (Quản lý công việc), Notes (Sổ tay/Knowledge Base), và Vault (Két bảo mật).

---

## 1. Mô hình Lưu trữ (Storage Layer)

Hệ thống hiện tại đang chạy tốt với Local JSON cho Phase 1. Tuy nhiên, khi hoàn thiện và đưa lên môi trường Production thực tế có nhiều dữ liệu, kiến trúc lưu trữ cần được phân mảnh rõ ràng dựa trên đặc tính của dữ liệu:

### 1.1. Task Management (PostgreSQL)
- **Đặc tính:** Dữ liệu có tính quan hệ cao (Task thuộc về Project, Assignee, có Tag, Event logs). Cần truy vấn (Filter/Sort) phức tạp.
- **Đề xuất:** Sử dụng **PostgreSQL** làm cơ sở dữ liệu chính.
- **ORM:** SQLAlchemy (trên FastAPI) xử lý các truy vấn. Đảm bảo cấu trúc bảng tối ưu Index cho các trường thường dùng để filter như `status`, `assignee`, `updated_at`.

### 1.2. Notes & Knowledge Base (PostgreSQL + pgvector)
- **Đặc tính:** Văn bản dài (Markdown), lưu trữ tri thức, cần tìm kiếm toàn văn bản (Full-text search) và tìm kiếm theo ngữ nghĩa (Semantic search) cho AI sau này.
- **Đề xuất:** Vẫn dùng PostgreSQL nhưng cài đặt thêm extension **`pgvector`**.
- **Lý do:** Cho phép lưu trữ vector embeddings của các Note. Khi người dùng hỏi AI: "Hôm trước tôi có ghi chú gì về dự án X", AI có thể query vector để tìm ra Note liên quan nhất mà không cần quét toàn bộ text.

### 1.3. Vault - Két bảo mật (Zero-Knowledge Architecture)
- **Đặc tính:** Chứa thông tin cực kỳ nhạy cảm (Mật khẩu, SSH Keys, Token). Backend hay Database Admin (DBA) cũng KHÔNG ĐƯỢC PHÉP đọc được.
- **Đề xuất:** **Client-side Encryption (Mã hóa đầu cuối)**.
- **Quy trình:** 
  1. Người dùng nhập Master Password. Trình duyệt dùng thuật toán `PBKDF2` hoặc `Argon2` để tạo ra khóa mã hóa (Key).
  2. Trình duyệt mã hóa (AES-256-GCM) nội dung Vault thành một đoạn mã hóa (Ciphertext) không thể đọc được.
  3. Gửi Ciphertext lên lưu ở Backend (PostgreSQL).
  4. Backend chỉ lưu trữ cục Ciphertext này. Nếu database bị hack, hacker cũng chỉ thấy chuỗi mã hoá vô nghĩa vì không có Master Password của người dùng.

---

## 2. Mô hình Triển khai (Deployment Model)

Để dễ dàng quản lý và triển khai (Deploy) theo đúng chuẩn DevOps:

- **Docker Compose (Single-node deployment):** Dành cho quy mô sử dụng cá nhân hoặc nhóm nhỏ (< 100 người).
  - Container 1: **Next.js Web** (Frontend + SSR).
  - Container 2: **FastAPI Core** (Backend Logic).
  - Container 3: **PostgreSQL** (Database chính).
  - Container 4: **Redis** (Dùng để cache tốc độ cao cho các filter query nặng, quản lý phiên bản token, và làm Broker nếu có chạy Background Worker).

- **Background Workers (Celery/ARQ):** 
  - Các tác vụ nặng như Kéo dữ liệu Jira (Sync Jira), Tính toán Vector Embeddings cho Note, Backup Database... phải được tách ra chạy ngầm (Background Job) để không làm nghẽn API chính.

---

## 3. Lộ trình Triển khai (Roadmap)

Nếu User ra lệnh *"Hãy triển khai kiến trúc mục tiêu"*, AI Agent sẽ thực hiện theo các bước sau:
1. Setup Docker Compose cho Postgres và Redis.
2. Viết Alembic Migrations để tạo bảng Task, Note, Vault trên Postgres.
3. Chuyển đổi mã nguồn `engine.ts` và `api.ts` từ việc đọc JSON sang gọi API Backend PostgreSQL.
4. Triển khai thuật toán mã hoá AES-256 GCM bằng thư viện Web Crypto API ở phía Frontend cho Vault.
5. Bật Celery Worker bên Python để xử lý Jira Sync ngầm.
