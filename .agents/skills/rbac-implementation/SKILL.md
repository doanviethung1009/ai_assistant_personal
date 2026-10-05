---
name: rbac-implementation
description: Checklist và hướng dẫn triển khai hệ thống phân quyền (RBAC - Role-Based Access Control) gồm Roles, Rules và Privileges. Dùng khi được yêu cầu thêm, sửa, hoặc kiểm tra logic phân quyền của dự án.
---

# Triển khai phân quyền (RBAC)

Đây là chuẩn mực khi thiết kế và viết code phân quyền cho hệ thống Builder AI Assistant (khi hệ thống chuyển từ Single-user sang Multi-user). Đừng tự chế lại bánh xe, hãy bám sát checklist và pattern này.

## Thuật ngữ
1. **User (Người dùng)**: Thực thể đăng nhập vào hệ thống.
2. **Role (Vai trò)**: Gom nhóm các quyền lại với nhau (VD: `admin`, `editor`, `viewer`).
3. **Privilege / Rule (Quyền hạn/Quy tắc)**: Quyền cụ thể để thực hiện một hành động trên một tài nguyên (VD: `task:create`, `vault:read`).

## Backend (`apps/core/`)

1. **Mô hình dữ liệu (Database)**
   - Khi thiết kế DB cho RBAC, cần bảng `users`, `roles`, `permissions` và các bảng nối (many-to-many) như `user_roles`, `role_permissions`.
   - Một người dùng có thể có nhiều Role. Một Role có thể có nhiều Permission.
   - Thêm cột `owner_id` (hoặc `created_by`) vào các resource bảng như `tasks`, `projects`, `notes` để phân biệt dữ liệu của ai.

2. **Middleware & Dependency Injection**
   - Viết các hàm helper trong `app/core/security.py` để kiểm tra quyền.
   - Tạo Dependency Injection cho FastAPI: `RequirePermission("task:delete")`. 
   - Token xác thực (VD: JWT) phải được giải mã tại đây để lấy ra `user_id` và danh sách quyền hạn.

3. **Gắn quyền vào Router và Service**
   - Trong `app/api/v1/`, các endpoint phải được gắn Dependency kiểm tra quyền cụ thể.
   - **Route-level Security**: Xác định người dùng có quyền gọi endpoint đó hay không. (Ví dụ: Chỉ `admin` mới gọi được `DELETE /system`).
   - **Row-level Security**: Xác định người dùng có quyền sửa/xoá dòng dữ liệu cụ thể đó hay không. BẮT BUỘC đưa logic này vào **Service layer** (Ví dụ: `if task.owner_id != current_user.id: raise ForbiddenException()`).

## Frontend (`apps/web/`)

4. **Quản lý Context / Store**
   - Khởi tạo session (JWT / Cookie).
   - Lấy danh sách Role và Permission của user hiện tại, bọc bằng một React Provider (`RBACProvider`) để mọi component đều có thể truy cập qua hook `useRBAC()`.

5. **Ẩn/Hiện UI theo quyền (Privilege-based UI)**
   - Tuyệt đối không hardcode Role kiểu `if (role === 'admin')`. HÃY kiểm tra theo quyền hạn cụ thể: `if (hasPermission('task:delete'))`.
   - Các nút xoá, sửa, xuất dữ liệu, cấu hình hệ thống phải được bọc trong hàm check quyền. Nếu không có quyền, không render (render `null`) thay vì chỉ làm mờ (disable).

6. **Bảo vệ Server Actions (`app/actions.ts`)**
   - Ẩn nút trên UI là chưa đủ vì user có thể gọi trực tiếp API/Action. Bất kỳ Server Action nào cũng phải có bước giải mã JWT/Session, lấy ra `user_id`, và từ chối xử lý nếu không đủ quyền.

## Checklist rà soát (Audit)
- [ ] Cơ sở dữ liệu: Các bảng resource (Tasks, Notes...) đã có trường lưu thông tin chủ sở hữu (`owner_id`) chưa?
- [ ] Giao diện (UI): Đã ẩn các tính năng mà người dùng không có quyền chưa (`hasPermission`)?
- [ ] Next.js Actions: Đã verify token/session và quyền hạn ở server-side trước khi gọi Core API chưa?
- [ ] FastAPI Backend: Đã gắn `RequirePermission` vào route chưa?
- [ ] FastAPI Backend: Đã kiểm tra Row-level security (dữ liệu của ai người nấy sửa) trong Service layer chưa?
