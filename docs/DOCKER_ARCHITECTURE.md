# Kiến trúc Docker & Hướng dẫn Triển khai (Docker Architecture)

Tài liệu này giải thích chi tiết cấu trúc các file Docker trong dự án, lý do tại sao chúng được cấu hình theo cách hiện tại (Best Practices), và cách người dùng kiểm soát việc triển khai (deploy).

---

## 1. Bản đồ File Hạ tầng (Infrastructure Files)

Hệ thống sử dụng Docker để cô lập môi trường và dễ dàng deploy. Dưới đây là các file cấu hình cốt lõi:

| File | Chức năng chính | Trạng thái (Mode) |
| --- | --- | --- |
| `docker-compose.yml` | Chứa cấu hình nền tảng chung: Database (Postgres+pgvector), Redis, API, Web. Định nghĩa Network, Volumes và Healthchecks. | Dev & Prod (Base) |
| `docker-compose.prod.yml` | File ghi đè (Override). Dùng để chèn thêm hoặc xoá bớt cấu hình của file gốc nhằm mục đích tối ưu cho chạy thực tế. | Production |
| `docker-compose.lan.yml` | Tương tự prod.yml nhưng cấu hình host mạng cho mạng LAN nội bộ. | LAN / Home Lab |
| `apps/core/Dockerfile` | Đóng gói Backend FastAPI (Python). | Đa môi trường |
| `apps/web/Dockerfile` | Đóng gói Frontend Next.js (Node.js). | Đa môi trường |

---

## 2. Giải mã cấu hình (Deep Dive Definitions)

### 2.1. Cấu hình Postgres & Redis (`docker-compose.yml`)
- **pgvector/pgvector:pg17**: Không dùng Postgres thường mà dùng bản có cài sẵn `pgvector`. Mục đích là để sau này làm RAG (AI tìm kiếm theo ngữ nghĩa dựa trên Vector Embeddings).
- **scram-sha-256**: Giao thức mã hoá mật khẩu mạnh nhất của Postgres hiện tại, chống lại các cuộc tấn công rò rỉ bộ nhớ.
- **Healthcheck**: Lệnh `pg_isready` và `redis-cli ping`. Đảm bảo Backend chỉ khởi động SAU KHI Database đã sẵn sàng, chống lỗi crash lúc khởi động.

### 2.2. Frontend Next.js (`apps/web/Dockerfile`)
- **Multi-stage build**: Chia làm nhiều bước (`deps`, `dev`, `builder`, `prod`) giúp tối ưu thời gian build (cache) và không mang file rác lên prod.
- **Standalone Mode (`.next/standalone`)**: Bình thường thư mục `node_modules` rất nặng (vài trăm MB đến cả GB). Next.js Standalone sẽ phân tích code và chỉ copy những file thực sự được dùng. Giúp Image cuối cùng siêu nhẹ.
- **Rootless (User `nextjs` uid 1001)**: Docker mặc định chạy bằng quyền Root (rất nguy hiểm nếu bị hack). Cấu hình này ép app chạy bằng quyền user thường, giới hạn tối đa thiệt hại.

### 2.3. Backend FastAPI (`apps/core/Dockerfile`)
- **Trình quản lý gói `uv`**: Thay vì dùng `pip` cực kỳ chậm, hệ thống dùng `uv` của Astral viết bằng Rust. Tốc độ cài đặt thư viện Python nhanh gấp 10-100 lần.
- **Venv nằm ở `/opt/venv`**: Tách biệt thư mục môi trường ảo ra khỏi thư mục source code (`/app`) để lúc dev dùng Bind Mount (map ổ cứng máy thật vào container) không bị ghi đè mất thư viện.
- **Tự động Migration (`alembic upgrade head`)**: Khởi động container là tự động tạo bảng DB nếu chưa có.

### 2.4. Khác biệt giữa Dev và Prod (`docker-compose.prod.yml`)
- Khi chạy Dev (`make dev`): Docker sẽ dùng **Bind Mount** (map thẳng folder máy thật vào container). Sửa code trên máy, container tự động reload (Hot-reload).
- Khi chạy Prod (`make prod-up`): Dùng thẻ `volumes: !override []`. Thẻ này lệnh cho Docker HỦY BỎ việc map folder máy thật, ép hệ thống phải đọc code ĐÃ ĐƯỢC ĐÓNG GÓI BÊN TRONG Image. Đảm bảo tính đóng gói an toàn tuyệt đối.

---

## 3. Các Lệnh Điều Khiển (Commands)

- Chạy chế độ phát triển (Có hot-reload): 
  ```bash
  make dev
  ```
- Build và chạy chế độ thực tế (Production):
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
  ```
- Dừng toàn bộ hệ thống:
  ```bash
  docker compose down
  ```
- Dừng và xoá luôn Database (Nguy hiểm - Reset toàn bộ):
  ```bash
  docker compose down -v
  ```
