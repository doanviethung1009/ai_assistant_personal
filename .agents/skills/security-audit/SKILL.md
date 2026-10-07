---
name: security-audit
description: Checklist kiểm toán bảo mật, rà soát lỗ hổng OWASP, phân quyền (RBAC) và mã hoá dữ liệu.
---

# Kỹ năng: Kiểm toán Bảo mật (Security Audit)

Dành cho **Security Auditor**. Kỹ năng này đóng vai trò như một "Máy Quét Lỗ Hổng" chạy bằng AI. Dùng để rà soát một đoạn code, một tính năng mới hoặc toàn bộ repo.

## Checklist Rà soát

### 1. Phân quyền & Định danh (Auth & RBAC)
- [ ] Mọi API (trừ public) có được bảo vệ bởi middleware xác thực (JWT/Session) không?
- [ ] Các thao tác Sửa/Xoá (PUT/DELETE) có kiểm tra quyền sở hữu (Is Owner) hoặc quyền quản trị (Is Admin) không? Xảy ra lỗi IDOR không?
- [ ] Nếu là API Frontend gọi Server Action, có kiểm tra quyền trước khi thao tác DB không?

### 2. An toàn Dữ liệu Đầu vào (Input Validation)
- [ ] Backend (FastAPI) có dùng Pydantic để validate và ép kiểu toàn bộ Payload/Query params không?
- [ ] Đầu vào từ Form (Frontend) có được làm sạch (Sanitize) để chống XSS khi render lại bằng `dangerouslySetInnerHTML` hay Markdown không?
- [ ] Có nguy cơ SQL Injection không? (Đảm bảo 100% dùng ORM SQLAlchemy, không dùng f-string query thô).

### 3. Mã hoá & Két Bảo mật (Cryptography)
- [ ] Tuyệt đối không lưu Plain-text Password. Dùng Argon2 hoặc bcrypt.
- [ ] Đối với tính năng Vault: Đảm bảo luồng mã hoá (AES-256-GCM) chạy 100% trên Trình duyệt (Client-side). Backend không lưu Key. 

### 4. Rò rỉ Thông tin (Data Leakage)
- [ ] Source code có bị hardcode `.env` key, API Key của bên thứ 3 không?
- [ ] Thông báo lỗi (Exception/500) trả về cho Client có bị lộ Stacktrace hoặc cấu trúc thư mục của Server không? Bắt buộc phải bọc lỗi an toàn.

## Báo cáo (Audit Report)
- Khi quét xong, tạo một Artifact (Bảng Markdown) liệt kê:
  | Mức độ (Risk) | Lỗ hổng (Vulnerability) | Vị trí (File:Line) | Đề xuất khắc phục (Fix) |
- Mức độ chia làm: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`. Đề xuất code patch ngay lập tức với các lỗi Critical.
