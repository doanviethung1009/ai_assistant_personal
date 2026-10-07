# Kịch bản Demo: Làm việc với Multi-Agent (Nhiều AI Agent)

Khi dự án lớn lên, việc nhồi nhét cho một AI làm từ A-Z (từ Thiết kế, Code, Test đến Merge) trong cùng một prompt thường dẫn đến rủi ro: AI bị "ảo giác" (hallucination), quên context, hoặc tự ý phá vỡ kiến trúc. Giải pháp tối ưu là **Multi-Agent Workflow** (Phân chia vai trò).

Dưới đây là Vòng đời hoàn thiện một Epic (Ví dụ: Tính năng Giỏ hàng) với 5 bước phối hợp:

---

## 📐 Bước 1: Thiết kế Kiến trúc (Software Architect)
**Mục tiêu:** Định hình luồng dữ liệu trước khi code.
> *"Đóng vai `@.agents/roles/software-architect.md`. Hãy phân tích yêu cầu tính năng Giỏ hàng, vẽ sơ đồ Sequence Diagram, định nghĩa API Contract và chốt với tôi trước khi làm tiếp."*

---

## 🛠 Bước 2: Phát triển Tính năng (Backend/Frontend/DBA)
**Mục tiêu:** Code trên các nhánh `feat/*` dựa trên bản thiết kế.
> *"Đóng vai `@.agents/roles/database-architect.md`. Chạy skill db-migration để tạo bảng CartItem."*
> 
> *"Đóng vai `@.agents/roles/backend-engineer.md`. Viết API `/api/v1/cart` theo đúng Contract của Architect."*
> 
> *"Đóng vai `@.agents/roles/frontend-engineer.md`. Code UI trang Giỏ hàng kết nối với API Backend. Tuyệt đối không đụng vào `apps/core/`."*

---

## 🕵️ Bước 3: Kiểm thử & Bảo mật (QA Tester / Security Auditor)
**Mục tiêu:** Soi rác, bắt lỗi và tấn công thử (Pentest) tính năng vừa code.
> *"Đóng vai `@.agents/roles/qa-tester.md`. Hãy chạy skill `qc-uat` kiểm tra kỹ luồng thêm vào giỏ hàng xem có lỗi vặt không."*
> 
> *"Đóng vai `@.agents/roles/security-auditor.md`. Hãy rà soát xem API Giỏ hàng có nguy cơ SQL Injection hay lỗi phân quyền (RBAC) không."*

---

## 👑 Bước 4: Duyệt Code & Gộp nhánh (Tech Lead)
**Mục tiêu:** Người giữ cửa (Gatekeeper) quyết định đưa code lên Production. Tại sao cần role này? Vì Dev và QA thường tập trung vào tính năng (Micro), còn Tech Lead sẽ nhìn vào tính ổn định toàn cục (Macro).
> *"Đóng vai `@.agents/roles/tech-lead.md`. Các Agent Dev và QA đã làm xong nhánh `feat/cart`. Hãy dùng skill `pr-review` để soát lại toàn bộ kiến trúc một lần cuối. Nếu đạt chuẩn, hãy Merge vào nhánh `main` và sinh Changelog."*

---

## 🐳 Bước 5: Triển khai (DevOps Engineer)
**Mục tiêu:** Đóng gói và đưa sản phẩm ra ngoài.
> *"Đóng vai `@.agents/roles/devops-engineer.md`. Chạy skill `docker-deploy` để build lại image của Web và Backend, đảm bảo mọi cấu hình an toàn."*

---

## 💡 Tổng kết sức mạnh của mô hình này:
1. **Phân lập Context:** Mỗi Agent chỉ đọc và thao tác trên phần việc của nó (Frontend không đụng Backend, QA không tự tiện sửa Database).
2. **Chéo kiểm tra (Cross-check):** Code do Dev-Agent viết sẽ bị bắt lỗi bởi QA-Agent và bị từ chối bởi TechLead-Agent nếu kém chất lượng.
3. **Quản lý rủi ro:** Bạn không bao giờ sợ AI làm hỏng nhánh `main` vì đã có luồng kiểm soát (Tech Lead) và tài liệu rõ ràng.
