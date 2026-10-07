---
name: architecture-design
description: Quy trình 5 bước thiết kế kiến trúc hệ thống (System Design) trước khi code.
---

# Kỹ năng: Thiết kế Kiến trúc (Architecture Design)

Kỹ năng này dành riêng cho **Software Architect**. Dùng khi bắt đầu một Module hoặc Epic lớn để đảm bảo luồng đi chính xác, không gây phá vỡ (breaking changes) kiến trúc hiện tại.

## Pipeline Thiết kế

### B1. Phân tích Yêu cầu (Requirement Analysis)
- Đọc kỹ Prompt của User. Trích xuất: 
  - Đâu là Data nguồn? Đâu là Điểm đích?
  - Module này nằm ở Frontend (Next.js) hay Backend (FastAPI)? Hay cả hai?

### B2. Kiểm tra Xung đột (Conflict Check)
- Đọc `TARGET_ARCHITECTURE.md` và `docs/project-review.md`. 
- Đánh giá xem thiết kế mới có vi phạm các nguyên tắc lõi hiện tại (VD: dùng sai Database, vi phạm quy tắc API REST) hay không.

### B3. Phác thảo Sơ đồ (Mermaid Drafting)
- Vẽ một trong hai loại sơ đồ bằng Markdown (`mermaid` block):
  - **Sequence Diagram:** (Biểu đồ Tuần tự) - Nếu quy trình có nhiều bước (VD: Đăng nhập -> Sinh Token -> Mã hoá).
  - **ERD (Entity Relationship):** Nếu tính năng liên quan đến việc tạo bảng Database mới.

### B4. Thiết kế Giao thức (API Contract)
- Định nghĩa rõ Endpoint, Method (GET/POST), Request Payload (JSON) và Response Body (JSON). 
- Đảm bảo tuân thủ kiểu trả về thống nhất của Backend.

### B5. Chốt phương án & Giao việc (Handoff)
- Trình bày bản thiết kế cho User phê duyệt (Approve).
- Khi User đồng ý, yêu cầu User gọi các Agent chuyên trách (Frontend/Backend) để tiến hành code. Ghi log thiết kế vào `docs/`.
