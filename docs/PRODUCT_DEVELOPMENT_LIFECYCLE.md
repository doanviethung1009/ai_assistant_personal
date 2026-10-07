# Quy trình Phát triển Sản phẩm (Product Development Lifecycle)

Tài liệu này hệ thống hoá toàn bộ quy trình phát triển từ lúc lên ý tưởng (Idea) cho đến lúc triển khai (Deployment) trên môi trường Production, dành riêng cho hệ thống Multi-Agent (Nhiều AI cùng làm việc).

Bất kỳ tính năng mới nào cũng **BẮT BUỘC** phải đi qua 6 bước (6-Step Pipeline) dưới đây. Cấm nhảy cóc.

---

## Bước 1: Khởi tạo và Phân vai (Ideation & Role Assignment)
- **Hành động:** User mô tả yêu cầu tính năng. Thay vì dùng Agent chung chung, User gọi đích danh nhân cách AI phù hợp từ `.agents/roles/`.
- **Ví dụ:** *"Hãy đóng vai `@frontend-engineer.md` để tạo trang Dashboard."*
- **Quy tắc tuân thủ:** Agent ngay lập tức nạp `docs/NEW_AGENT_ONBOARDING.md` và đọc Handoff State để hiểu bối cảnh dự án.

## Bước 2: Thiết kế và Lập trình (Implementation)
- **Hành động:** Agent bắt đầu viết code.
- **Quy tắc tuân thủ:**
  - Áp dụng các luật ngầm từ `.agents/rules/` (Backend / Frontend Conventions).
  - Sử dụng các kỹ năng rập khuôn (Skills) như `add-entity` (Thêm bảng) hoặc `rbac-implementation` (Phân quyền) để đảm bảo không sai sót kiến trúc.
  - Phải tuân thủ `docs/TARGET_ARCHITECTURE.md` (Không dùng công nghệ ngoài luồng).

## Bước 3: Tự Kiểm thử Cục bộ (Local QA / Self-Check)
- **Hành động:** Trước khi báo cáo code xong, Agent **BẮT BUỘC** phải tự chạy quy trình kiểm thử chất lượng.
- **Quy tắc tuân thủ:** 
  - Gọi skill `.agents/skills/qc-uat/SKILL.md`.
  - Kiểm tra UI, bắt lỗi Validation Form, test giới hạn dữ liệu (Pagination), và xử lý lỗi 500/Timeout thân thiện.
  - Cập nhật mọi tài liệu API (`API_REFERENCE.md`) hoặc Project Blueprint.

## Bước 4: Đẩy Code và Tạo Pull Request (Branching & PR)
- **Hành động:** Đẩy code lên môi trường Git.
- **Quy tắc tuân thủ:**
  - Chạy skill `.agents/skills/git-commit/SKILL.md`.
  - **Tuyệt đối không push thẳng lên `main`.**
  - Checkout nhánh mới (`feat/xxx`), commit theo chuẩn Conventional Commits, và push lên remote.
  - Báo cáo cho User để mở Pull Request.

## Bước 5: Kiểm duyệt Code (PR Review & Security Check)
- **Hành động:** Soi lỗi chéo (Cross-review) trước khi cho phép Merge.
- **Quy tắc tuân thủ:**
  - User gọi Agent đóng vai `@qa-tester.md` và chạy skill `pr-review`.
  - QA Agent sẽ quét file rác, bắt lỗi bảo mật, chạy `make lint`, `tsc --noEmit`.
  - Chỉ khi QA Agent ra quyết định 🟢 **APPROVED**, PR mới được phép gộp (Merge) vào `main`.

## Bước 6: Triển khai (CI/CD & Go-Live)
- **Hành động:** Đưa code lên môi trường UAT và Production.
- **Quy tắc tuân thủ:**
  - Bám sát `docs/git-workflow.md` và `docs/deploy-runbook.md`.
  - Chạy lệnh `make promote-uat` (Chỉ chấp nhận Fast-Forward từ `main`).
  - Chạy Smoke Test trên server UAT.
  - Gắn tag phiên bản và chạy `make promote-prod` để Go-Live.

---
**💡 Châm ngôn của dự án:** *"Nhanh là tốt, nhưng không bao giờ được hy sinh Kiến trúc và Bảo mật. Mọi dòng code sinh ra đều phải có người kiểm duyệt (dù đó là AI hay Human)."*
