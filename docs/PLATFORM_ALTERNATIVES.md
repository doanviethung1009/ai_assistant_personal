# Đánh giá Nền tảng & Đề xuất Thay thế (Platform Alternatives)

Tài liệu này phân tích các "Platform" (Nền tảng/Công nghệ) lõi đang được sử dụng trong dự án và đề xuất các phương án công nghệ thay thế tương đương trên thị trường, giúp bạn có cái nhìn tổng quan khi muốn chuyển đổi hoặc mở rộng hệ thống.

---

## 1. Frontend Platform (Giao diện)
**🔹 Đang sử dụng:** `Next.js 15` (React) + `TailwindCSS v4`. 
- **Lý do:** Chuẩn ngành, cộng đồng lớn, hỗ trợ Server-Side Rendering (SSR) tốt nhất cho SEO và bảo mật API Key.

**💡 Các Nền tảng Thay thế:**
- **Vite + React (SPA):** 
  - *Khi nào dùng:* Khi bạn muốn tách biệt 100% Backend và Frontend, build ra HTML tĩnh siêu nhẹ. 
  - *Nhược điểm:* Không có SSR, gọi API lộ Key, Load trang đầu chậm hơn.
- **SvelteKit:** 
  - *Khi nào dùng:* Muốn code gọn gàng, ít boilerplate, tốc độ render cực kỳ nhanh vì không dùng Virtual DOM.
- **HTMX + Alpine.js:** 
  - *Khi nào dùng:* Dành cho những ai thích code thuần Backend (gắn thẳng logic vào HTML, không cần học React). Rất phù hợp nếu dùng chung với Django/Go.

---

## 2. Backend Core Platform (Lõi Xử lý)
**🔹 Đang sử dụng:** `FastAPI` (Python 3.12) + `SQLAlchemy` (ORM).
- **Lý do:** FastAPI là framework nhanh nhất của Python hiện tại. Python cực kỳ mạnh về AI/Data (phục vụ xử lý Note, RAG).

**💡 Các Nền tảng Thay thế:**
- **Golang (Gin / Fiber):** 
  - *Khi nào dùng:* Cần hiệu năng **cao tuyệt đối** và tốn ít RAM. Go chạy nhanh gấp 10 lần Python và build ra 1 file nhị phân duy nhất (Deploy siêu nhẹ).
- **Node.js (NestJS / Express):** 
  - *Khi nào dùng:* Khi team chỉ rành Javascript/Typescript. Có thể dùng chung 1 ngôn ngữ cho cả Web lẫn Backend.
- **Rust (Actix-web / Axum):** 
  - *Khi nào dùng:* Cần độ an toàn bộ nhớ tuyệt đối và hiệu năng ngang C++. Đổi lại, cực kỳ khó học và khó tuyển dev.

---

## 3. Database Platform (Lưu trữ Dữ liệu)
**🔹 Đang sử dụng:** `PostgreSQL` (Kèm `pgvector`).
- **Lý do:** Là vua của relational database mã nguồn mở. Hỗ trợ JSONB xuất sắc và `pgvector` hoàn hảo cho việc lưu trữ trí tuệ AI.

**💡 Các Nền tảng Thay thế:**
- **MongoDB (NoSQL):** 
  - *Khi nào dùng:* Dữ liệu thay đổi cấu trúc liên tục (Unstructured Data), không có tính quan hệ chặt chẽ. Rất hợp với các hệ thống cào dữ liệu (Crawler).
- **Turso (LibSQL / SQLite phân tán):** 
  - *Khi nào dùng:* Không muốn tốn tài nguyên chạy Server Database nặng nề. SQLite nằm thẳng trong file hệ thống nhưng đồng bộ Cloud thời gian thực.
- **Supabase / Firebase (BaaS):** 
  - *Khi nào dùng:* Muốn Backend-as-a-Service, hệ thống cung cấp sẵn API cho DB và Realtime WebSockets, bỏ qua bước tự code Backend.

---

## 4. Deployment & Infra Platform (Triển khai & Vận hành)
**🔹 Đang sử dụng:** `Docker Compose` (Máy chủ ảo - VPS).
- **Lý do:** Docker đóng gói môi trường hoàn hảo, chạy ở đâu cũng giống nhau. Compose giúp quản lý 3-4 containers đơn giản bằng 1 file lệnh.

**💡 Các Nền tảng Thay thế:**
- **Kubernetes (K8s):**
  - *Khi nào dùng:* Dự án Scale-up cực lớn, có hàng chục Microservices và cần chạy trên nhiều Node (máy chủ) khác nhau, tự động Cân bằng tải (Load Balancer). Quá phức tạp cho dự án cá nhân.
- **AWS ECS / Fargate / Google Cloud Run (Container-as-a-Service):**
  - *Khi nào dùng:* Vẫn dùng Docker nhưng không muốn phải tự quản lý máy chủ VPS (OS, Security, RAM). AWS/Google sẽ tự cấp phát tài nguyên để chạy container của bạn. Chi phí cao.
- **Podman:**
  - *Khi nào dùng:* Thay thế trực tiếp (Drop-in replacement) cho Docker. Chạy ở chế độ Rootless hoàn toàn từ lõi, bảo mật tốt hơn Docker rất nhiều. Rất được các cty khối Tài chính ưu chuộng.
- **NixOS / Nix:**
  - *Khi nào dùng:* Một tư duy deploy hoàn toàn khác. Thay vì dùng Docker để đóng gói, bạn dùng một ngôn ngữ khai báo (`.nix`) để định nghĩa cấu hình toàn bộ hệ điều hành. Tuyệt đối đồng nhất.
