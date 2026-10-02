---
description: Bắt buộc đọc trạng thái dự án khi bắt đầu session mới
---

# AI Role: Session Handoff

Mỗi khi người dùng yêu cầu tiếp tục công việc hoặc thông báo đây là session mới (hay chuyển máy):

1. Bạn **BẮT BUỘC** phải dùng tool `view_file` để đọc nội dung file `docs/AI_HANDOFF_STATE.md`.
2. Dựa vào nội dung file đó, bạn sẽ hiểu rõ kiến trúc hiện tại, các chức năng đã xây dựng xong (JIRA Sync, Quản lý Tag, Phân trang Team, v.v.) và tránh việc phá hỏng logic (như logic chia task cá nhân và task team).
3. Nếu người dùng yêu cầu update document, bạn hãy update trực tiếp vào `docs/AI_HANDOFF_STATE.md` để đảm bảo context luôn mới nhất cho các session AI tiếp theo.
