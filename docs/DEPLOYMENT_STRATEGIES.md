# Tư vấn Chiến lược Triển khai (Deployment Strategies)

Tài liệu này tổng hợp các phương pháp triển khai (Deploy) hệ thống từ môi trường chạy thử (Local) đến thực tế (Production), so sánh ưu/nhược điểm để người dùng dễ dàng lựa chọn.

---

## 1. Local Development (NPM & Uv) - Chạy trực tiếp
Đây là cách bạn đang chạy trên máy tính cá nhân để code, test và sử dụng.

- **Thao tác:**
  - Frontend: `npm run dev` (Khởi chạy Next.js).
  - Backend: `uv sync` và chạy `uvicorn` qua script.
- **Dành cho ai:** Hoàn toàn **lý tưởng cho MỤC ĐÍCH CÁ NHÂN**. Nếu bạn chỉ dùng công cụ này một mình trên máy cá nhân, việc giữ cách chạy Local là cực kỳ tốt và tiện lợi. Không cần phải setup Docker hay Server phức tạp nếu không có nhu cầu chia sẻ nội bộ/public.
- **Ưu điểm:**
  - Nhanh gọn, không ngốn RAM máy tính để ảo hóa Docker.
  - Sửa code là thấy ngay (Live-reload).
  - Dữ liệu lưu thẳng ra file JSON cục bộ, backup bằng tay cực dễ.
- **Nhược điểm:**
  - Khó chia sẻ link cho người khác dùng chung. Dễ gặp lỗi môi trường nếu copy sang máy tính thứ 2 chưa cài Python/Nodejs.

---

## 2. Local/Server Docker Compose (Khuyên dùng)
Cách đóng gói toàn bộ hệ thống vào container, dùng chung file `docker-compose.yml`.

- **Thao tác:**
  - Lệnh: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
- **Ưu điểm:**
  - **Đồng nhất:** Chạy trên máy bạn hay Server VPS (Ubuntu/CentOS) đều giống hệt nhau.
  - **Bảo mật:** Database không mở port public, chỉ giao tiếp nội bộ trong mạng ảo (Docker bridge network).
  - Khởi động lại khi sập (Auto-restart) cực tốt.
- **Nhược điểm:**
  - Chi phí Server ban đầu (Cần VPS khoảng 2GB RAM tối thiểu để gánh cả Next.js và Postgres).
  - Tốc độ build tốn chút thời gian.

---

## 3. Serverless (Vercel Frontend + Render Backend)
Tách Frontend và Backend ra triển khai ở các dịch vụ Cloud miễn phí/giá rẻ.

- **Thao tác:**
  - Frontend: Đẩy code lên GitHub, link với Vercel. Vercel tự động build và cấp domain HTTPS.
  - Backend: Triển khai FastAPI lên Render (hoặc Railway, Heroku). Dùng Database Managed (như Supabase hoặc Neon DB).
- **Ưu điểm:**
  - Rẻ hoặc Miễn phí (Hưởng Free-tier của Vercel/Render).
  - Không cần lo quản trị Server (No DevOps overhead).
  - Auto-scale (Tự động mở rộng khi có nhiều người truy cập).
- **Nhược điểm:**
  - Cold Start (Lần truy cập đầu tiên sau một thời gian app "ngủ" sẽ tốn khoảng 3-5 giây để khởi động lại).
  - Phụ thuộc hoàn toàn vào dịch vụ bên thứ 3. Khó cấu hình bảo mật IP khắt khe giữa Frontend và Backend.

---

## 4. Lời Khuyên & Tổng Kết

- **Đang phát triển (Hiện tại):** Tiếp tục dùng `npm run dev` như đang làm để có tốc độ code nhanh nhất.
- **Khi làm xong Phase 1 & muốn tự dùng an toàn:** Thuê một VPS (DigitalOcean/Linode giá ~5$/tháng) và áp dụng cách số 2 (**Docker Compose**). Kiến trúc hệ thống hiện tại đã được cấu hình tối ưu 100% cho việc này.
- **Khi muốn đem khoe/public không tốn phí:** Sử dụng cách số 3 (**Vercel + Supabase**). Tuy nhiên, bạn sẽ phải từ bỏ các cấu hình đặc thù (như Local JSON) để chuyển sang dùng hoàn toàn Database Cloud.
