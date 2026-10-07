---
name: db-migration
description: Quy trình an toàn để tạo, chỉnh sửa và áp dụng Database Migration (Alembic) cho PostgreSQL. Bắt buộc dùng khi có yêu cầu thêm bảng, thêm cột hoặc đổi kiểu dữ liệu.
---

# Quy trình Database Migration An Toàn

1. **Khởi tạo:** Chạy `alembic revision --autogenerate -m "tên_migration"` sau khi sửa SQLAlchemy models.
2. **Kiểm tra thủ công:** Agent PHẢI mở file migration vừa tạo ra để soi. Alembic đôi khi tự sinh code sai (VD: xóa bảng nhầm do đổi tên).
3. **Luật Backward-Compatible:** Không bao giờ xoá cột (DROP COLUMN) hoặc đổi tên cột mà chưa làm 2 bước: Thêm cột mới -> Viết script chuyển dữ liệu -> Xoá cột cũ ở bản release sau.
4. **Luật Khoá DB (Locking):** Tránh các lệnh `ALTER TABLE` nặng trên bảng có hàng triệu record mà không dùng `CONCURRENTLY`.
5. **Kiểm thử:** Chạy `alembic upgrade head` trên local test DB trước khi cho phép commit.
