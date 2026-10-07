---
name: docker-deploy
description: Quy trình kiểm tra và triển khai hệ thống thông qua Docker Compose. Dùng khi cấu hình hạ tầng, sửa Dockerfile hoặc chuẩn bị đẩy code lên Production.
---

# Quy trình Docker Deploy

1. **Kiểm tra Multistage Build:** Đảm bảo Dockerfile có tối thiểu 2 bước (Builder và Runner) để giảm dung lượng file image cuối cùng.
2. **Kiểm tra Bảo mật (Rootless):** Image tuyệt đối không được chạy dưới quyền `root`. Phải thiết lập `USER node` (với Nodejs) hoặc `USER app` (với Python).
3. **Build cục bộ:** Chạy `make prod-build` để xem ảnh có build thành công không. Cấm đẩy code nếu build lỗi.
4. **Dry-run Compose:** Dựng container ở môi trường local bằng `docker-compose -f docker-compose.prod.yml up -d` để xác nhận các biến môi trường (ENV) được gài đúng.
