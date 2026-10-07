---
name: pr-review
description: Quy trình AI thực hiện Code Review và QA cho một Pull Request (PR) hoặc nhánh tính năng (Feature Branch) trước khi cho phép gộp (merge) vào nhánh main. Chuyên dùng cho mô hình Multi-Agent/Multi-User, đảm bảo không có lỗi, rác, hoặc vi phạm kiến trúc lọt vào hệ thống.
---

# Quy trình AI PR Review & QA

Mục đích: Đóng vai trò là một "Gatekeeper" (Người gác cổng) cực kỳ khắt khe. AI Reviewer có nhiệm vụ soi xét từng dòng code thay đổi trong nhánh hiện tại so với `main`. 

Khi User yêu cầu "Hãy review PR này" hoặc "Kiểm tra nhánh này trước khi merge", Agent **BẮT BUỘC** thực hiện checklist 5 bước sau:

## 1. Kiểm tra Rác và Dữ liệu nhạy cảm (Sanity Check)
- [ ] Soi kỹ các file mới thêm vào: Không được phép commit các file nháp tạm thời (vd: `fix_bug.py`, `test.json`, `patch_*.js`). Các file này phải được bỏ vào `.gitignore` hoặc xóa đi.
- [ ] Không có file `.env` chứa mật khẩu thật, API keys hoặc Secrets lọt vào PR.
- [ ] Không để sót các lệnh debug `console.log(...)` vô nghĩa hoặc `print(...)` rác ở Backend.

## 2. Kiểm tra Kiến trúc (Architecture Guard)
- [ ] Code có bám sát bản thiết kế mục tiêu (`docs/TARGET_ARCHITECTURE.md`) không?
- [ ] Nếu có sửa đổi Database Schema, file Migration (Alembic) đã được tạo đúng chuẩn chưa? Có chứa mã nguy hiểm (DROP TABLE không có lý do) không?
- [ ] Logic lấy dữ liệu có tuân thủ cơ chế Pagination (Phân trang limit/offset) không, hay đang `SELECT *` kéo toàn bộ DB làm nghẽn RAM?

## 3. Tuân thủ Quy chuẩn (Convention)
- [ ] Code Backend/Frontend có tuân theo đúng luật trong `.agents/rules/` không? (Vd: Naming convention, Dependency injection ở FastAPI).
- [ ] Mọi hàm phức tạp phải có Docstring/Comment giải thích **TẠI SAO** (WHY) làm vậy. Cấm viết comment giải thích cái vòng lặp for đang làm gì.

## 4. Thực thi Kiểm thử Tự động (Automated QA)
Agent **PHẢI** tự động mở Terminal chạy các lệnh sau (nếu dự án hỗ trợ) để chứng minh code không lỗi:
- [ ] Backend: Chạy `make lint` hoặc `ruff check apps/core`.
- [ ] Frontend: Chạy `cd apps/web && npx tsc --noEmit` để rà soát lỗi Type.
- [ ] Chạy bộ Smoke Test `make smoke` (nếu có).
- [ ] Bắt buộc Build thử Next.js production `cd apps/web && npm run build` xem có sập không.

## 5. Ra Quyết định (Decision)
Sau khi quét xong, AI Agent phải trả lời bằng 1 bản Báo Cáo rõ ràng:
- 🟢 **APPROVED:** Nếu mọi thứ hoàn hảo. Hướng dẫn User thực hiện lệnh gộp (Merge).
- 🟡 **CHANGES REQUESTED:** Nếu có lỗi nhỏ (Thiếu comment, sai type). Tự đề xuất (Propose) code fix luôn cho User.
- 🔴 **REJECTED:** Vi phạm nghiêm trọng (Xoá data bậy bạ, rò rỉ token). Cảnh báo đỏ cho User.
